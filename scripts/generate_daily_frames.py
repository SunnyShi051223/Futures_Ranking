"""Generate daily backtest snapshots in parallel.

The script is intentionally data-driven: pass a JSON list through --strategy-specs,
or omit it to discover all equity_curve_*.csv files in --data-dir.
Existing frames are skipped so interrupted batches can resume.
"""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.font_manager import FontProperties
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

STRATEGIES = {}
INITIAL_CAPITAL = 500_000.0
TABLES = {}
X_MIN = X_MAX = None
Y_MIN = Y_MAX = None
FONT = None


def choose_font():
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf", r"C:\Windows\Fonts\simsun.ttc"):
        if Path(path).exists():
            return FontProperties(fname=path)
    return FontProperties()


def read_csv(path: Path, usecols):
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            return pd.read_csv(path, encoding=encoding, usecols=usecols)
        except UnicodeDecodeError:
            continue
    raise UnicodeError(f"Cannot decode {path}")


def default_specs(data_path: Path):
    keys = sorted(path.stem.removeprefix("equity_curve_") for path in data_path.glob("equity_curve_*.csv"))
    colors = ["#16806b", "#c34e55", "#4768a8", "#9b6ab0", "#d17a22", "#3b8f8f"]
    return {key: {"title": key.replace("_", " ").title(), "color": colors[i % len(colors)]} for i, key in enumerate(keys)}


def init_worker(data_dir: str, frame_dir: str, specs_json: str, initial_capital: float):
    """Load all CSVs once in each process; individual frames only do filtering/drawing."""
    global TABLES, X_MIN, X_MAX, Y_MIN, Y_MAX, FONT, STRATEGIES, INITIAL_CAPITAL
    data_path = Path(data_dir)
    INITIAL_CAPITAL = float(initial_capital)
    STRATEGIES = json.loads(specs_json) if specs_json else default_specs(data_path)
    TABLES = {}
    for key in STRATEGIES:
        equity = read_csv(data_path / f"equity_curve_{key}.csv", ["timestamp", "equity"])
        positions = read_csv(data_path / f"positions_{key}.csv", ["时间", "品种", "合约", "开仓时点", "标记价", "浮动盈亏", "保证金收益率"])
        trades = read_csv(data_path / f"trades_{key}.csv", ["品种", "开仓时点", "平仓时点", "开仓价", "平仓价", "净盈亏"])
        equity["timestamp"] = pd.to_datetime(equity["timestamp"])
        positions["时间"] = pd.to_datetime(positions["时间"])
        positions["开仓时点"] = pd.to_datetime(positions["开仓时点"])
        trades["开仓时点"] = pd.to_datetime(trades["开仓时点"])
        trades["平仓时点"] = pd.to_datetime(trades["平仓时点"])
        TABLES[key] = (equity.sort_values("timestamp"), positions.sort_values("时间"), trades.sort_values("开仓时点"))
    all_times = pd.concat([table[0]["timestamp"] for table in TABLES.values()])
    all_values = pd.concat([table[0]["equity"] for table in TABLES.values()])
    X_MIN, X_MAX = all_times.min(), all_times.max()
    Y_MIN, Y_MAX = float(all_values.min()), float(all_values.max())
    FONT = choose_font()
    plt.rcParams["axes.unicode_minus"] = False
    Path(frame_dir).mkdir(parents=True, exist_ok=True)


def money(value):
    return "—" if pd.isna(value) else f"¥{float(value):,.0f}"


def pct(value):
    return "—" if pd.isna(value) else f"{float(value):+.1%}"


def short_time(value):
    return pd.Timestamp(value).strftime("%H:%M") if pd.notna(value) else "—"


def draw_table(ax, rows, columns, widths, fontsize=7.6, row_height=0.115):
    ax.axis("off")
    if not rows:
        ax.text(0.02, 0.62, "无记录", fontproperties=FONT, fontsize=fontsize + 1, color="#667085")
        return
    table = ax.table(cellText=rows, colLabels=columns, colWidths=widths, loc="upper left", cellLoc="left", bbox=[0, 0, 1, 1])
    table.auto_set_font_size(False)
    table.set_fontsize(fontsize)
    for (row, _), cell in table.get_celld().items():
        cell.set_height(row_height)
        cell.set_edgecolor("#d9dee7")
        cell.PAD = 0.025
        if row == 0:
            cell.set_facecolor("#eef2f7")
            cell.set_text_props(weight="bold", color="#263245", fontproperties=FONT)
        else:
            cell.set_facecolor("#ffffff" if row % 2 else "#f8fafc")
            cell.set_text_props(color="#263245", fontproperties=FONT)


def snapshot(day_text: str, index: int, frame_dir: str):
    day = pd.Timestamp(day_text).normalize()
    frame_path = Path(frame_dir) / f"frame_{index:04d}_{day:%Y%m%d}.png"
    if frame_path.exists():
        return index, "skipped"
    row_count = len(STRATEGIES)
    fig = plt.figure(figsize=(18, max(12, 5.0 * row_count)), facecolor="#ffffff")
    outer = GridSpec(row_count, 1, figure=fig, hspace=0.22)
    fig.suptitle(f"交易日快照  {day:%Y-%m-%d}", fontproperties=FONT, fontsize=21, fontweight="bold", y=0.995)
    for row_no, (key, meta) in enumerate(STRATEGIES.items()):
        equity, positions, trades = TABLES[key]
        color = meta.get("color", "#16806b")
        title = meta.get("title", key.replace("_", " ").title())
        sub = GridSpecFromSubplotSpec(2, 2, subplot_spec=outer[row_no], width_ratios=[1.08, 1.55], height_ratios=[0.32, 0.68], wspace=0.12, hspace=0.08)
        ax_curve = fig.add_subplot(sub[:, 0])
        ax_info = fig.add_subplot(sub[0, 1]); ax_info.axis("off")
        ax_table = fig.add_subplot(sub[1, 1])
        day_end = day + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
        history = equity[equity["timestamp"] <= day_end]
        if history.empty:
            history = equity.iloc[:1]
        current = history.iloc[-1]
        ax_curve.plot(history["timestamp"], history["equity"], color=color, linewidth=2.0)
        ax_curve.scatter([current["timestamp"]], [current["equity"]], color=color, s=44, zorder=4)
        ax_curve.axvline(current["timestamp"], color=color, alpha=0.22, linewidth=1.1)
        x_pad = pd.Timedelta(days=18)
        y_pad = max((Y_MAX - Y_MIN) * 0.07, INITIAL_CAPITAL * 0.03)
        ax_curve.set_xlim(X_MIN - x_pad, X_MAX + x_pad)
        ax_curve.set_ylim(Y_MIN - y_pad, Y_MAX + y_pad)
        ax_curve.axhline(INITIAL_CAPITAL, color="#9aa4b2", linestyle="--", linewidth=1)
        ax_curve.set_title(title, fontproperties=FONT, fontsize=14, loc="left", color=color, pad=8)
        ax_curve.set_ylabel("组合权益（元）", fontproperties=FONT)
        ax_curve.grid(axis="y", color="#e7ebf0", linewidth=0.8)
        ax_curve.spines[["top", "right"]].set_visible(False)
        ax_curve.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=4, maxticks=6))
        ax_curve.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax_curve.tick_params(axis="x", rotation=20)
        for label in ax_curve.get_xticklabels() + ax_curve.get_yticklabels():
            label.set_fontproperties(FONT)
        rows = positions[positions["时间"] <= day_end]
        if rows.empty:
            current_positions = positions.iloc[0:0]
        else:
            current_positions = rows[rows["时间"] == rows["时间"].max()].copy()
            current_positions = current_positions[current_positions["品种"].fillna("").astype(str).str.strip() != ""].sort_values("浮动盈亏", ascending=False)
        opened = trades[trades["开仓时点"].dt.normalize() == day]
        closed = trades[trades["平仓时点"].dt.normalize() == day]
        realized = float(closed["净盈亏"].sum()) if not closed.empty else 0.0
        info = [f"期末权益  {money(current['equity'])}", f"累计收益  {money(float(current['equity']) - INITIAL_CAPITAL)} ({pct(float(current['equity']) / INITIAL_CAPITAL - 1)})", f"当日已实现盈亏  {money(realized)}", f"当前持仓  {len(current_positions)}    当日开仓 {len(opened)}    当日平仓 {len(closed)}"]
        ax_info.text(0, 0.92, "\n".join(info), va="top", fontproperties=FONT, fontsize=11, linespacing=1.45, color="#263245")
        combined = []
        for _, item in current_positions.head(10).iterrows():
            combined.append(["持仓", str(item.get("品种", "")), str(item.get("合约", "")), short_time(item.get("开仓时点")), money(item.get("标记价")), money(item.get("浮动盈亏")), pct(item.get("保证金收益率"))])
        for _, trade in pd.concat([opened, closed]).head(12).iterrows():
            closed_trade = pd.notna(trade.get("平仓时点")) and trade["平仓时点"].normalize() == day
            combined.append(["平仓" if closed_trade else "开仓", str(trade.get("品种", "")), "", short_time(trade.get("平仓时点" if closed_trade else "开仓时点")), money(trade.get("平仓价" if closed_trade else "开仓价")), money(trade.get("净盈亏")) if closed_trade else "—", "—"])
        columns = ["状态", "品种/动作", "合约/品种", "时间", "价格", "浮盈/已实现", "保证金收益率"]
        if combined:
            draw_table(ax_table, combined, columns, [0.10, 0.20, 0.16, 0.13, 0.15, 0.18, 0.14])
        else:
            ax_table.axis("off")
            ax_table.text(0, 0.7, "当前无持仓，今日无交易", fontproperties=FONT, fontsize=10, color="#667085")
    fig.text(0.01, 0.01, "资金曲线、持仓与交易来自回测输出 CSV；平仓计入已实现盈亏，未平仓显示浮动盈亏。", fontproperties=FONT, fontsize=9, color="#667085")
    fig.savefig(frame_path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return index, "written"


def main():
    parser = argparse.ArgumentParser(description="Generate daily backtest frames in parallel")
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--frame-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 1))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--initial-capital", type=float, default=500_000.0)
    parser.add_argument("--strategy-specs", default="", help="JSON list or mapping of strategy specs")
    args = parser.parse_args()
    args.frame_dir.mkdir(parents=True, exist_ok=True)
    if args.strategy_specs:
        parsed = json.loads(args.strategy_specs)
        specs = parsed if isinstance(parsed, list) else [{"key": key, **value} for key, value in parsed.items()]
        strategy_specs = {spec["key"]: spec for spec in specs}
    else:
        strategy_specs = default_specs(args.data_dir)
    if not strategy_specs:
        raise FileNotFoundError(f"{args.data_dir} 中没有 equity_curve_*.csv")
    dates = set()
    for key in strategy_specs:
        frame = read_csv(args.data_dir / f"equity_curve_{key}.csv", ["timestamp"])
        dates.update(pd.to_datetime(frame["timestamp"]).dt.normalize().tolist())
    dates = sorted(dates)
    if args.limit:
        dates = dates[:args.limit]
    jobs = [(day.isoformat(), index) for index, day in enumerate(dates, 1)]
    worker_count = max(1, min(args.workers, len(jobs) or 1))
    specs_json = json.dumps(strategy_specs, ensure_ascii=False)
    print(f"交易日 {len(jobs)} 天；并行进程 {worker_count}；策略数 {len(strategy_specs)}；已有帧将跳过。", flush=True)
    completed = written = skipped = 0
    with ProcessPoolExecutor(max_workers=worker_count, initializer=init_worker, initargs=(str(args.data_dir.resolve()), str(args.frame_dir.resolve()), specs_json, args.initial_capital)) as executor:
        futures = [executor.submit(snapshot, day, index, str(args.frame_dir.resolve())) for day, index in jobs]
        for future in as_completed(futures):
            _, status = future.result()
            completed += 1
            written += status == "written"
            skipped += status == "skipped"
            if completed == 1 or completed % 25 == 0 or completed == len(futures):
                print(f"{completed}/{len(futures)} 完成（新生成 {written}，跳过 {skipped}）", flush=True)
    print(f"完成：新生成 {written} 帧，跳过已存在 {skipped} 帧。", flush=True)


if __name__ == "__main__":
    main()
