"""MySQL repository for normalized WT8 strategy equity rows."""
from datetime import datetime, timedelta

from .base import RankingRepository
from .margin_utils import build_margin_index, margin_rate_at

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
            "equity": float(row[4]), "signal": row[5] or "", "position": int(row[6] or 0),
            "close_volume": float(row[7]) if len(row) > 7 and row[7] is not None else None,
            "volume": float(row[8]) if len(row) > 8 and row[8] is not None else None,
            "turnover": float(row[9]) if len(row) > 9 and row[9] is not None else None,
            "available": float(row[10]) if len(row) > 10 and row[10] is not None else None}

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
        price_mode = self.strategy_id == "price_only"
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute(f"""SELECT e.timestamp,e.instrument,e.contract,e.price,e.equity,e.signal_text,e.position,
                                  e.close_volume,e.volume,e.turnover,e.available,latest.first_time
                FROM {self.table} e
                JOIN (SELECT instrument,MAX(timestamp) AS latest_time,MIN(timestamp) AS first_time
                      FROM {self.table} WHERE timestamp<=%s GROUP BY instrument) latest
                  ON latest.instrument=e.instrument AND latest.latest_time=e.timestamp
                ORDER BY e.instrument""", (target,))
            end_rows = cur.fetchall()
            ending = {row[1]: (self._row(row[:-1]), row[-1]) for row in end_rows}
            history = {instrument: {} for instrument in ending}

            window_days = 14
            cutoff = target - timedelta(days=window_days)
            cur.execute(f"""SELECT timestamp,instrument,contract,price,equity,signal_text,position,
                                  close_volume,volume,turnover,available
                FROM {self.table} WHERE timestamp>=%s AND timestamp<=%s
                ORDER BY instrument,timestamp""", (cutoff, target))
            for raw in cur.fetchall():
                row = self._row(raw)
                history[row["instrument"]][row["timestamp"]] = row

            def start_for(instrument):
                end_row, _first_time = ending[instrument]
                rows = sorted(history[instrument].values(), key=lambda item: item["timestamp"])
                if end_row["timestamp"] not in history[instrument]:
                    rows.append(end_row)
                    rows.sort(key=lambda item: item["timestamp"])
                dates = sorted({row["timestamp"].date() for row in rows if row["timestamp"] <= end_row["timestamp"]})
                if len(dates) < 6:
                    return None, True
                start_date = dates[-6]
                start_target = datetime.combine(start_date, end_row["timestamp"].time())
                start_row = None
                for row in rows:
                    if row["timestamp"].date() == start_date and row["timestamp"] <= start_target:
                        start_row = row
                return start_row, False

            while True:
                unresolved = []
                for instrument, (_end_row, first_time) in ending.items():
                    start_row, needs_more_history = start_for(instrument)
                    if needs_more_history and cutoff > first_time:
                        unresolved.append(instrument)
                if not unresolved:
                    break
                window_days *= 2
                cutoff = target - timedelta(days=window_days)
                names = ",".join(["%s"] * len(unresolved))
                params = (*unresolved, cutoff, target)
                cur.execute(f"""SELECT timestamp,instrument,contract,price,equity,signal_text,position,
                                      close_volume,volume,turnover,available
                    FROM {self.table} WHERE instrument IN ({names}) AND timestamp>=%s AND timestamp<=%s
                    ORDER BY instrument,timestamp""", params)
                for raw in cur.fetchall():
                    row = self._row(raw)
                    history[row["instrument"]][row["timestamp"]] = row
                if window_days >= 4096:
                    break

            # Seed each rolling history window with its latest earlier trade and margin observations.
            cur.execute(f"""SELECT e.timestamp,e.instrument,e.contract,e.price,e.equity,e.signal_text,e.position,
                                  e.close_volume,e.volume,e.turnover,e.available
                FROM {self.table} e
                JOIN (SELECT instrument,MAX(timestamp) AS ref_time FROM {self.table}
                      WHERE timestamp<%s AND signal_text IN ('BK','SP') AND price>0 AND turnover>0
                        AND ((signal_text='BK' AND volume>0) OR (signal_text='SP' AND close_volume>0))
                      GROUP BY instrument) ref
                  ON ref.instrument=e.instrument AND ref.ref_time=e.timestamp""", (cutoff,))
            prior_trade_rows = [self._row(raw) for raw in cur.fetchall()]
            cur.execute(f"""SELECT e.timestamp,e.instrument,e.contract,e.price,e.equity,e.signal_text,e.position,
                                  e.close_volume,e.volume,e.turnover,e.available
                FROM {self.table} e
                JOIN (SELECT instrument,MAX(timestamp) AS ref_time FROM {self.table}
                      WHERE timestamp<%s AND position=1 AND price>0 AND available IS NOT NULL AND equity>available
                      GROUP BY instrument) ref
                  ON ref.instrument=e.instrument AND ref.ref_time=e.timestamp""", (cutoff,))
            prior_margin_rows = [self._row(raw) for raw in cur.fetchall()]
        finally:
            conn.close()

        result = []
        for instrument, (row, _first_time) in ending.items():
            start_row, _needs_more_history = start_for(instrument)
            if start_row is None:
                continue
            starting_value = start_row["price"] if price_mode else start_row["equity"]
            ending_value = row["price"] if price_mode else row["equity"]
            if starting_value is None or ending_value is None or starting_value <= 0:
                continue
            amount = ending_value - starting_value
            starting_margin = None
            if not price_mode:
                historical_rows = [
                    item for item in history[instrument].values()
                    if item["timestamp"] <= start_row["timestamp"]
                ]
                historical_rows.extend(
                    item for item in prior_trade_rows + prior_margin_rows
                    if item["instrument"] == instrument and item["timestamp"] <= start_row["timestamp"]
                )
                multipliers, margin_histories, margin_times = build_margin_index({instrument: historical_rows})
                multiplier = multipliers.get(instrument)
                margin_rate = margin_rate_at(instrument, start_row["timestamp"], margin_histories, margin_times)
                if start_row["price"] and multiplier and margin_rate:
                    starting_margin = start_row["price"] * multiplier * margin_rate
                if not starting_margin or starting_margin <= 0:
                    continue
            item = {
                **row,
                "lookback_timestamp": start_row["timestamp_iso"],
                "data_time": row["timestamp_iso"],
                "return_amount": amount,
                "starting_equity": starting_value,
                "ending_equity": ending_value,
                "starting_margin": starting_margin,
                "return_rate": amount / (starting_value if price_mode else starting_margin) * 100,
                "lag_minutes": round((target - row["timestamp"]).total_seconds() / 60, 1),
                "stale": (target - row["timestamp"]).total_seconds() > 10800,
            }
            item.pop("timestamp", None)
            result.append(item)

        result.sort(key=lambda item: (-item["return_rate"], item["instrument"]))
        for rank, item in enumerate(result, 1):
            item["rank"] = rank
            item["in_top_k"] = rank <= top_k
            for key in ("equity", "return_amount", "return_rate"):
                item[key] = round(item[key], 4 if key == "return_rate" else 2)
            item["starting_equity"] = round(item["starting_equity"], 2)
            item["ending_equity"] = round(item["ending_equity"], 2)
            if item["starting_margin"] is not None:
                item["starting_margin"] = round(item["starting_margin"], 2)
            if item["price"] is not None:
                item["price"] = round(item["price"], 6)
        return {
            "strategy": self.strategy_id,
            "strategy_name": self.strategy_name,
            "timestamp": target.isoformat(timespec="seconds"),
            "lookback_trading_days": 5,
            "ranking_mode": "price" if price_mode else "strategy",
            "initial_capital": self.settings.initial_capital,
            "top_k": top_k,
            "total": len(result),
            "items": result,
        }

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
