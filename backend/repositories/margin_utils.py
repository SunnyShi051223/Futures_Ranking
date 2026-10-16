"""Helpers for expressing a strategy's WT8 profit as return on one-lot margin."""

from bisect import bisect_right
from collections import defaultdict
from statistics import median


def build_margin_index(rows_by_instrument):
    """Infer each instrument's contract multiplier and dated WT8 margin-rate history.

    Rows need timestamp, signal, price, turnover, volume, close_volume, equity,
    available, and position fields. All estimates are derived from observations
    already present in the supplied series; callers still apply an as-of cutoff.
    """
    multipliers = {}
    histories = {}
    for instrument, rows in rows_by_instrument.items():
        multiplier_samples = []
        for row in rows:
            signal = row.get("signal", row.get("signal_text", ""))
            if signal not in {"BK", "SP"}:
                continue
            price = row.get("price")
            turnover = row.get("turnover")
            qty_key = "volume" if signal == "BK" else "close_volume"
            quantity = row.get(qty_key)
            if price and turnover and quantity:
                multiplier_samples.append(float(turnover) / (float(price) * float(quantity)))
        if multiplier_samples:
            multipliers[instrument] = float(median(multiplier_samples))

        multiplier = multipliers.get(instrument)
        if not multiplier:
            continue
        rates_by_time = defaultdict(list)
        for row in rows:
            timestamp = row.get("timestamp")
            price = row.get("price")
            equity = row.get("equity")
            available = row.get("available")
            if not timestamp or not row.get("position") or not price or available is None or equity is None:
                continue
            margin = float(equity) - float(available)
            notional = float(price) * multiplier
            rate = margin / notional if notional > 0 else None
            if rate is not None and 0.001 <= rate <= 0.50:
                rates_by_time[timestamp].append(rate)
        points = sorted((timestamp, float(median(rates))) for timestamp, rates in rates_by_time.items())
        if points:
            histories[instrument] = points

    times = {instrument: [point[0] for point in points] for instrument, points in histories.items()}
    return multipliers, histories, times


def margin_rate_at(instrument, timestamp, histories, times):
    """Return the latest observed margin rate at or before timestamp."""
    history = histories.get(instrument, [])
    index = bisect_right(times.get(instrument, []), timestamp) - 1
    return history[index][1] if index >= 0 else None

