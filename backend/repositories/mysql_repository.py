"""MySQL repository for normalized WT8 strategy equity rows."""
from datetime import datetime

from .base import RankingRepository

STRATEGY_TABLES = {
    "price_only": "ranking_buyhold",
    "buy_hold": "ranking_buyhold",
    "sar_long": "ranking_sar",
    "macd_long": "ranking_macd",
}


def table_for_strategy(strategy_id: str) -> str:
    try:
        return STRATEGY_TABLES[strategy_id]
    except KeyError as exc:
        raise ValueError(f"unknown strategy: {strategy_id}") from exc


class MySQLRankingRepository(RankingRepository):
    def __init__(self, settings, strategy_id: str, strategy_name: str):
        self.settings = settings
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self.table = table_for_strategy(strategy_id)
        self.contract_names = []

    def _connect(self):
        import mysql.connector
        return mysql.connector.connect(host=self.settings.mysql_host, port=self.settings.mysql_port,
            user=self.settings.mysql_user, password=self.settings.mysql_password,
            database=self.settings.mysql_database, autocommit=True)

    @staticmethod
    def _row(row):
        return {"timestamp": row[0], "timestamp_iso": row[0].isoformat(timespec="seconds"),
            "instrument": row[1], "contract": row[2] or "", "price": float(row[3]) if row[3] is not None else None,
            "equity": float(row[4]), "signal": row[5] or "", "position": int(row[6] or 0)}

    def periods(self, limit=10000):
        limit = max(1, min(int(limit), 20000)); conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(DISTINCT timestamp),MIN(timestamp),MAX(timestamp) FROM {self.table}")
            count, first, last = cur.fetchone()
            cur.execute(f"SELECT DISTINCT timestamp FROM {self.table} ORDER BY timestamp DESC LIMIT %s", (limit,))
            items = sorted(row[0].isoformat(timespec="seconds") for row in cur.fetchall())
            return {"items": items, "count": count or 0, "first": first.isoformat(timespec="seconds") if first else None, "last": last.isoformat(timespec="seconds") if last else None}
        finally: conn.close()

    def contracts(self):
        conn = self._connect()
        try:
            cur = conn.cursor(); cur.execute(f"SELECT DISTINCT instrument FROM {self.table} ORDER BY instrument")
            self.contract_names = [row[0] for row in cur.fetchall()]
            return [{"instrument": name} for name in self.contract_names]
        finally: conn.close()

    def ranking(self, timestamp: str, top_k: int = 10, start_timestamp: str = None):
        target = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        start = datetime.fromisoformat(start_timestamp.replace("Z", "+00:00")).replace(tzinfo=None) if start_timestamp else None
        price_mode = self.strategy_id == "price_only"
        if price_mode and start is None:
            raise ValueError("纯价格排序需要选择起始和结束时点")
        if start and start >= target:
            raise ValueError("起始时点必须早于结束时点")
        conn = self._connect()
        try:
            cur = conn.cursor()
            if start:
                start_column = "s.price" if price_mode else "s.equity"
                after_column = "sa.price" if price_mode else "sa.equity"
                fallback = "NULL" if price_mode else "%s"
                cur.execute(f"""SELECT e.timestamp,e.instrument,e.contract,e.price,e.equity,e.signal_text,e.position,
                    COALESCE({start_column}, {after_column}, {fallback}) AS starting_value
                    FROM {self.table} e
                    JOIN (SELECT instrument,MAX(timestamp) latest_time FROM {self.table}
                        WHERE timestamp<=%s GROUP BY instrument) ending
                      ON ending.instrument=e.instrument AND ending.latest_time=e.timestamp
                    LEFT JOIN (SELECT instrument,MAX(timestamp) latest_time FROM {self.table}
                        WHERE timestamp<=%s GROUP BY instrument) start_rows
                      ON start_rows.instrument=e.instrument
                    LEFT JOIN {self.table} s
                      ON s.instrument=start_rows.instrument AND s.timestamp=start_rows.latest_time
                    LEFT JOIN (SELECT instrument,MIN(timestamp) earliest_time FROM {self.table}
                        WHERE timestamp>%s GROUP BY instrument) start_after
                      ON start_after.instrument=e.instrument
                    LEFT JOIN {self.table} sa
                      ON sa.instrument=start_after.instrument AND sa.timestamp=start_after.earliest_time
                    ORDER BY e.instrument""", ((target, start, start) if price_mode else (self.settings.initial_capital, target, start, start)))
                raw_rows = cur.fetchall()
                rows = [(self._row(row[:7]), float(row[7]) if row[7] is not None else None) for row in raw_rows]
            else:
                cur.execute(f"""SELECT e.timestamp,e.instrument,e.contract,e.price,e.equity,e.signal_text,e.position
                    FROM {self.table} e JOIN (SELECT instrument,MAX(timestamp) latest_time FROM {self.table}
                    WHERE timestamp<=%s GROUP BY instrument) ending
                    ON ending.instrument=e.instrument AND ending.latest_time=e.timestamp
                    ORDER BY e.instrument""", (target,))
                rows = [(self._row(row), self.settings.initial_capital) for row in cur.fetchall()]
        finally: conn.close()
        result = []
        for row, starting_equity in rows:
            if price_mode and (starting_equity is None or row["price"] is None or not starting_equity):
                continue
            ending_value = row["price"] if price_mode else row["equity"]
            amount = ending_value - starting_equity
            item = {**row, "data_time": row["timestamp_iso"], "return_amount": amount,
                "starting_equity": starting_equity, "ending_equity": ending_value,
                "return_rate": amount / starting_equity * 100 if starting_equity else 0,
                "lag_minutes": round((target-row["timestamp"]).total_seconds()/60, 1),
                "stale": (target-row["timestamp"]).total_seconds() > 10800,
                }
            item.pop("timestamp", None)
            result.append(item)
        if price_mode:
            result.sort(key=lambda item: (-item["return_rate"], item["instrument"]))
        else:
            # Rank one-contract strategy performance by interval profit amount.
            result.sort(key=lambda item: (-item["return_amount"], item["instrument"]))
        for rank, item in enumerate(result, 1):
            item["rank"] = rank
            item["in_top_k"] = rank <= top_k
            for key in ("equity", "return_amount", "return_rate"):
                item[key] = round(item[key], 4 if key == "return_rate" else 2)
            item["starting_equity"] = round(item["starting_equity"], 2)
            item["ending_equity"] = round(item["ending_equity"], 2)
            if item["price"] is not None: item["price"] = round(item["price"], 6)
        return {"strategy": self.strategy_id, "strategy_name": self.strategy_name,
            "start_timestamp": start.isoformat(timespec="seconds") if start else None,
            "timestamp": target.isoformat(timespec="seconds"), "ranking_mode": "price" if price_mode else "strategy",
            "initial_capital": self.settings.initial_capital, "top_k": top_k, "total": len(result), "items": result}

    def series(self, instrument: str):
        conn = self._connect()
        try:
            cur = conn.cursor(); cur.execute(f"SELECT timestamp,instrument,contract,price,equity,signal_text,position FROM {self.table} WHERE instrument=%s ORDER BY timestamp", (instrument,))
            rows = [self._row(row) for row in cur.fetchall()]
        finally: conn.close()
        return [{"timestamp": row["timestamp_iso"], "equity": round(row["equity"], 2),
            "return_rate": round((row["equity"]-self.settings.initial_capital)/self.settings.initial_capital*100, 4),
            "price": row["price"], "signal": row["signal"], "position": row["position"], "contract": row["contract"]} for row in rows]

    def trade_events(self, instrument: str, start_timestamp: str, end_timestamp: str):
        start = datetime.fromisoformat(start_timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        end = datetime.fromisoformat(end_timestamp.replace("Z", "+00:00")).replace(tzinfo=None)
        if start >= end:
            raise ValueError("交易明细时间区间无效")
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f"""SELECT timestamp,contract,signal_text,price,close_volume,volume,
                turnover,fee,trade_pnl,equity,position FROM {self.table}
                WHERE instrument=%s AND timestamp >= %s AND timestamp <= %s
                  AND signal_text IN ('BK','SP','SK','BP') ORDER BY timestamp""",
                (instrument, start, end))
            rows = cur.fetchall()
        finally:
            conn.close()
        labels = {"BK": ("买入开仓", "多头"), "SP": ("卖出平仓", "多头"),
                  "SK": ("卖出开仓", "空头"), "BP": ("买入平仓", "空头")}
        events = []
        for row in rows:
            timestamp, contract, signal, price, close_volume, volume, turnover, fee, pnl, equity, position = row
            action, side = labels[signal]
            events.append({
                "timestamp": timestamp.isoformat(timespec="seconds"), "instrument": instrument,
                "contract": contract or "", "signal": signal, "action": action, "side": side,
                "price": float(price) if price is not None else None,
                "volume": float(close_volume or volume or 0),
                "turnover": float(turnover) if turnover is not None else None,
                "fee": float(fee) if fee is not None else None,
                "realized_pnl": float(pnl) if pnl is not None else None,
                "equity": float(equity), "position": int(position or 0),
            })
        return events
