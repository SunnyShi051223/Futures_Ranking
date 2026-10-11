"""WT8 CSV reader and time-aligned ranking repository."""
import csv
import re
from bisect import bisect_right
from datetime import datetime
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

    def preload(self):
        """Load and index all files once during WSGI worker startup."""
        self._load()
        return len(self._data or {})

    def _load(self):
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

    def _read_file(self, path: Path, instrument: str):
        rows = []
        for encoding in ("gb18030", "gbk", "utf-8-sig"):
            try:
                with path.open("r", encoding=encoding, errors="strict", newline="") as handle:
                    reader = csv.reader(handle)
                    header = next(reader, None)
                    raw_rows = reader
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
                "price": price,
                "equity": equity,
                "available": _number(raw[13] if len(raw) > 13 else None),
                "fee": _number(raw[11] if len(raw) > 11 else None),
                "pnl": _number(raw[12] if len(raw) > 12 else None),
                "position": position,
            })
        rows.sort(key=lambda row: row["timestamp"])
        return rows

    def periods(self, limit=10000):
        data = self._load()
        timestamps = sorted({row["timestamp"] for rows in data.values() for row in rows})
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

    def ranking(self, timestamp: str, top_k: int = 10):
        data = self._load()
        target = _parse_time(timestamp)
        if target is None:
            raise ValueError("invalid timestamp")
        result = []
        for instrument, rows in data.items():
            row = self._at_or_before(rows, target)
            if row is None:
                continue
            item = dict(row)
            item.pop("timestamp", None)
            item["return_amount"] = row["equity"] - self.initial_capital
            item["return_rate"] = (item["return_amount"] / self.initial_capital) * 100
            item["data_time"] = row["timestamp_iso"]
            item["lag_minutes"] = round((target - row["timestamp"]).total_seconds() / 60, 1)
            item["stale"] = item["lag_minutes"] > 180
            result.append(item)
        result.sort(key=lambda item: (-item["return_rate"], item["instrument"]))
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
            "timestamp": target.isoformat(timespec="seconds"),
            "initial_capital": self.initial_capital,
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
