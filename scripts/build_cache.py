import csv
import json
import re
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
CAPITAL = 500000
DATE_FORMATS = ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M")


def number(value):
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"---", "--", "-"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_time(value):
    text = str(value or "").strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).isoformat(timespec="seconds")
        except ValueError:
            pass
    return None


def instrument(path):
    return re.sub(r"\s+", "", re.sub(r"_小时.*?_信号明细$", "", path.stem))


def build(strategy, folder):
    data = {}
    periods = set()
    for path in sorted((BASE / "data" / folder).glob("*.csv")):
        name = instrument(path)
        rows = []
        with path.open("r", encoding="gb18030", errors="ignore", newline="") as handle:
            reader = csv.reader(handle)
            next(reader, None)
            for raw in reader:
                if len(raw) < 15:
                    continue
                timestamp = parse_time(raw[1])
                equity = number(raw[14])
                if timestamp is None or equity is None:
                    continue
                rows.append({"timestamp": timestamp, "instrument": name, "contract": str(raw[2]).strip(), "price": number(raw[7]), "equity": equity, "signal": str(raw[3]).strip(), "position": 0})
                periods.add(timestamp)
        if rows:
            data[name] = rows
    target = BASE / "data" / "cache" / f"{strategy}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"strategy": strategy, "initial_capital": CAPITAL, "periods": sorted(periods), "data": data}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{strategy}: {len(data)} contracts, {len(periods)} periods, {target.stat().st_size / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    build("buy_hold", "小时Buy_And_Hold")
    build("sar_long", "小时SAR多头")
    build("macd_long", "小时MACD多头")
