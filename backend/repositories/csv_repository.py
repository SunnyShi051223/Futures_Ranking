"""WT8 CSV reader and time-aligned ranking repository."""
import csv
import json
import re
from bisect import bisect_right
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from .base import RankingRepository


DATE_FORMATS = (
    "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M",
)


def _clean(value: Any) -> str:
    return str(value or "").replace("\ufeff", "").strip()


def _number(value: Any):
    text = _clean(value).replace(",", "")
    if not text or text in {"---", "--", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_time(value: Any):
    text = _clean(value)
    if "T" in text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _instrument_name(path: Path) -> str:
    name = path.stem
    # WT8 exports use one of the strategy-specific suffixes after the
    # instrument name. Keep the parser tolerant of future strategy names.
    name = re.sub(r"_小时.*?_信号明细$", "", name)
    name = re.sub(r"_信号明细$", "", name)
    return re.sub(r"\s+", "", name)


class CsvRankingRepository(RankingRepository):
    def __init__(self, directory: Path, initial_capital: float = 500000,
                 strategy_id: str = "sar_long", strategy_name: str = "1小时 SAR 多头收益"):
        self.directory = Path(directory)
        self.initial_capital = float(initial_capital)
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name
        self._data = None
        self._signature = None
        self.contract_names = []
        self._periods_cache = None
        self._cache_path = self.directory.parent / "cache" / f"{self.strategy_id}.json"

    def preload(self):
        """Load and index all files once during WSGI worker startup."""
        self._load()
        return len(self._data or {})

    def _load(self):
        if self._cache_path.exists():
            try:
                payload = json.loads(self._cache_path.read_text(encoding="utf-8"))
                data = {}
                for instrument, rows in payload.get("data", {}).items():
                    for row in rows:
                        row["timestamp"] = _parse_time(row.get("timestamp"))
                        row["timestamp_iso"] = row["timestamp"].isoformat(timespec="seconds")
                    data[instrument] = rows
                self._data = data
                self.contract_names = sorted(data)
                self._periods_cache = [_parse_time(value) for value in payload.get("periods", [])]
                self._signature = ("cache", self._cache_path.stat().st_mtime_ns)
                return data
            except (OSError, ValueError, TypeError, KeyError):
                pass
        paths = sorted(self.directory.glob("*.csv"))
        signature = tuple((str(path), path.stat().st_mtime_ns, path.stat().st_size) for path in paths)
        if self._data is not None and signature == self._signature:
            return self._data
        data = {}
        for path in paths:
            instrument = _instrument_name(path)
            if not instrument:
                continue
            rows = self._read_file(path, instrument)
            if rows:
                data[instrument] = rows
        self._data = data
        self._signature = signature
        self.contract_names = sorted(data)
        return data

    def _iter_rows(self, path: Path, instrument: str):
        """Yield normalized rows without materializing a CSV file first."""
        for encoding in ("gb18030", "gbk", "utf-8-sig"):
            try:
                with path.open("r", encoding=encoding, errors="strict", newline="") as handle:
                    reader = csv.reader(handle)
                    next(reader, None)
                    position = 0
                    for raw in reader:
                        if len(raw) < 8:
                            continue
                        timestamp = _parse_time(raw[1])
                        if timestamp is None:
                            continue
                        signal = _clean(raw[3])
                        if signal == "BK":
                            position = 1
                        elif signal in {"SP", "SK", "BP"}:
                            position = 0
                        equity = _number(raw[14] if len(raw) > 14 else None)
                        if equity is None:
                            continue
                        yield {
                            "timestamp": timestamp,
                            "timestamp_iso": timestamp.isoformat(timespec="seconds"),
                            "instrument": instrument,
                            "contract": _clean(raw[2] if len(raw) > 2 else ""),
                            "signal": signal,
                            "signal_row": _clean(raw[4] if len(raw) > 4 else ""),
                            "buy_sell": _clean(raw[5] if len(raw) > 5 else ""),
                            "close_open": _clean(raw[6] if len(raw) > 6 else ""),
                            "price": _number(raw[7] if len(raw) > 7 else None),
                            "equity": equity,
                            "available": _number(raw[13] if len(raw) > 13 else None),
                            "fee": _number(raw[11] if len(raw) > 11 else None),
                            "pnl": _number(raw[12] if len(raw) > 12 else None),
                            "position": position,
                        }
                return
            except (UnicodeDecodeError, OSError):
                continue

    def _read_file(self, path: Path, instrument: str):
        rows = []
        raw_rows = []
        for encoding in ("gb18030", "gbk", "utf-8-sig"):
            try:
                with path.open("r", encoding=encoding, errors="strict", newline="") as handle:
                    reader = csv.reader(handle)
                    next(reader, None)
                    raw_rows = list(reader)
                break
            except (UnicodeDecodeError, OSError):
                raw_rows = []
        if not raw_rows:
            return rows
        position = 0
        for raw in raw_rows:
            if len(raw) < 8:
                continue
            timestamp = _parse_time(raw[1])
            if timestamp is None:
                continue  # includes WT8 合计/汇总 rows
            signal = _clean(raw[3])
            if signal == "BK":
                position = 1
            elif signal in {"SP", "SK", "BP"}:
                position = 0
            equity = _number(raw[14] if len(raw) > 14 else None)
            if equity is None:
                continue
            price = _number(raw[7] if len(raw) > 7 else None)
            rows.append({
                "timestamp": timestamp,
                "timestamp_iso": timestamp.isoformat(timespec="seconds"),
                "instrument": instrument,
                "contract": _clean(raw[2] if len(raw) > 2 else ""),
                "signal": signal,
                "signal_row": _clean(raw[4] if len(raw) > 4 else ""),
                "buy_sell": _clean(raw[5] if len(raw) > 5 else ""),
                "close_open": _clean(raw[6] if len(raw) > 6 else ""),
                "close_volume": _number(raw[8] if len(raw) > 8 else None),
                "volume": _number(raw[9] if len(raw) > 9 else None),
                "turnover": _number(raw[10] if len(raw) > 10 else None),
                "price": price,
                "equity": equity,
                "fee": _number(raw[11] if len(raw) > 11 else None),
                "pnl": _number(raw[12] if len(raw) > 12 else None),
                "available": _number(raw[13] if len(raw) > 13 else None),
                "position": position,
            })
        rows.sort(key=lambda row: row["timestamp"])
        return rows

    def periods(self, limit=10000):
        data = self._load()
        if self._periods_cache is None:
            timestamps = set()
            for rows in data.values():
                timestamps.update(row["timestamp"] for row in rows)
            self._periods_cache = sorted(timestamps)
        timestamps = self._periods_cache
        selected = timestamps[-limit:]
        return {
            "items": [t.isoformat(timespec="seconds") for t in selected],
            "count": len(timestamps),
            "first": timestamps[0].isoformat(timespec="seconds") if timestamps else None,
            "last": timestamps[-1].isoformat(timespec="seconds") if timestamps else None,
        }

    def contracts(self):
        self._load()
        return [{"instrument": name} for name in self.contract_names]

    def _at_or_before(self, rows, target):
        times = [row["timestamp"] for row in rows]
        index = bisect_right(times, target) - 1
        return rows[index] if index >= 0 else None

    @staticmethod
    def _at_or_after(rows, target):
        """Use the first available observation when a series starts later."""
        if target is None:
            return None
        times = [row["timestamp"] for row in rows]
        index = bisect_right(times, target - timedelta(microseconds=1))
        return rows[index] if index < len(rows) else None

    def ranking(self, timestamp: str, top_k: int = 10, start_timestamp: str = None):
        data = self._load()
        target = _parse_time(timestamp)
        if target is None:
            raise ValueError("invalid timestamp")
        start = _parse_time(start_timestamp) if start_timestamp else None
        price_mode = self.strategy_id == "price_only"
        if price_mode and start is None:
            raise ValueError("纯价格排序需要选择起始和结束时点")
        if start and start >= target:
            raise ValueError("起始时点必须早于结束时点")
        result = []
        for instrument, rows in data.items():
            row = self._at_or_before(rows, target)
            if row is None:
                continue
            start_row = self._at_or_before(rows, start) if start else None
            if price_mode and start_row is None:
                start_row = self._at_or_after(rows, start)
            if price_mode and (start_row is None or start_row.get("price") is None or row.get("price") is None):
                continue
            starting_equity = (start_row["price"] if price_mode else (start_row["equity"] if start_row else self.initial_capital))
            ending_value = row["price"] if price_mode else row["equity"]
            item = dict(row)
            item.pop("timestamp", None)
            item["starting_equity"] = starting_equity
            item["ending_equity"] = ending_value
            item["return_amount"] = ending_value - starting_equity
            item["return_rate"] = (item["return_amount"] / starting_equity) * 100 if starting_equity else 0
            item["data_time"] = row["timestamp_iso"]
            item["lag_minutes"] = round((target - row["timestamp"]).total_seconds() / 60, 1)
            item["stale"] = item["lag_minutes"] > 180
            result.append(item)
        if price_mode:
            result.sort(key=lambda item: (-item["return_rate"], item["instrument"]))
        else:
            # The requested leaderboard is based on each contract's one-lot P&L.
            result.sort(key=lambda item: (-item["return_amount"], item["instrument"]))
        for rank, item in enumerate(result, 1):
            item["rank"] = rank
            item["in_top_k"] = rank <= top_k
            item["equity"] = round(item["equity"], 2)
            item["return_amount"] = round(item["return_amount"], 2)
            item["return_rate"] = round(item["return_rate"], 4)
            if item["price"] is not None:
                item["price"] = round(item["price"], 6)
        return {
            "strategy": self.strategy_id,
            "strategy_name": self.strategy_name,
            "start_timestamp": start.isoformat(timespec="seconds") if start else None,
            "timestamp": target.isoformat(timespec="seconds"),
            "initial_capital": self.initial_capital,
            "ranking_mode": "price" if price_mode else "strategy",
            "top_k": top_k,
            "total": len(result),
            "items": result,
        }

    def series(self, instrument: str):
        data = self._load()
        rows = data.get(instrument, [])
        result = []
        for row in rows:
            result.append({
                "timestamp": row["timestamp_iso"],
                "equity": round(row["equity"], 2),
                "return_rate": round((row["equity"] - self.initial_capital) / self.initial_capital * 100, 4),
                "price": row["price"],
                "signal": row["signal"],
                "position": row["position"],
                "contract": row["contract"],
            })
        return result

    def trade_events(self, instrument: str, start_timestamp: str, end_timestamp: str):
        """Return actual WT8 order signal rows within an inclusive time range."""
        start = _parse_time(start_timestamp)
        end = _parse_time(end_timestamp)
        if start is None or end is None or start >= end:
            raise ValueError("交易明细时间区间无效")
        paths = [path for path in self.directory.glob("*.csv") if _instrument_name(path) == instrument]
        if not paths:
            raise KeyError(f"找不到品种 {instrument} 的原始明细 CSV")
        rows = self._read_file(paths[0], instrument)
        labels = {
            "BK": ("买入开仓", "多头"),
            "SP": ("卖出平仓", "多头"),
            "SK": ("卖出开仓", "空头"),
            "BP": ("买入平仓", "空头"),
        }
        events = []
        for row in rows:
            if not (start <= row["timestamp"] <= end) or row["signal"] not in labels:
                continue
            action, side = labels[row["signal"]]
            trade_volume = row.get("close_volume") or 0
            if trade_volume <= 0:
                trade_volume = row.get("volume") or 0
            events.append({
                "timestamp": row["timestamp_iso"], "instrument": instrument,
                "contract": row["contract"], "signal": row["signal"],
                "action": action, "side": side, "price": row["price"],
                "volume": trade_volume, "turnover": row.get("turnover"),
                "fee": row.get("fee"), "realized_pnl": row.get("pnl"),
                "equity": row["equity"], "position": row["position"],
            })
        return events
