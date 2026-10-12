"""Create local MySQL schema and import all WT8 CSV files.

PowerShell: $env:MYSQL_PASSWORD='your-password'; python scripts/import_mysql.py
"""
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

import mysql.connector

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from config import settings

HOST = settings.mysql_host
PORT = settings.mysql_port
USER = settings.mysql_user
PASSWORD = settings.mysql_password
DATABASE = settings.mysql_database
STRATEGIES = {"buy_hold": "小时Buy_And_Hold", "sar_long": "小时SAR多头", "macd_long": "小时MACD多头"}
TABLES = {"buy_hold": "ranking_buyhold", "sar_long": "ranking_sar", "macd_long": "ranking_macd"}


def number(value):
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"---", "--", "-"}: return None
    try: return float(text)
    except ValueError: return None


def parse_time(value):
    text = str(value or "").strip()
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M"):
        try: return datetime.strptime(text, fmt)
        except ValueError: pass
    return None


def instrument(path):
    return re.sub(r"\s+", "", re.sub(r"_小时.*?_信号明细$", "", path.stem))


def ensure_schema():
    conn = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD)
    cur = conn.cursor(); cur.execute(f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"); conn.commit(); cur.close(); conn.close()
    conn = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, database=DATABASE)
    cur = conn.cursor()
    template = (BASE / "db" / "schema.sql").read_text(encoding="utf-8")
    for table in TABLES.values():
        cur.execute(template.replace("{table_name}", table))
        # Keep existing installations compatible when new trade columns are added.
        for column, definition in {
            "close_volume": "DECIMAL(20,4) NULL",
            "volume": "DECIMAL(20,4) NULL",
            "turnover": "DECIMAL(20,4) NULL",
            "fee": "DECIMAL(20,4) NULL",
            "trade_pnl": "DECIMAL(20,4) NULL",
            "available": "DECIMAL(20,4) NULL",
        }.items():
            try:
                cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            except mysql.connector.Error as exc:
                if exc.errno != 1060:  # duplicate column; safe on re-runs
                    raise
    conn.commit(); cur.close(); conn.close()


def import_strategy(conn, strategy, folder):
    table = TABLES[strategy]
    cur = conn.cursor()
    cur.execute(f"TRUNCATE TABLE {table}")
    sql = f"""INSERT INTO {table}
        (instrument,contract,timestamp,price,equity,signal_text,position,close_volume,volume,turnover,fee,trade_pnl,available)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE contract=VALUES(contract),price=VALUES(price),
        equity=VALUES(equity),signal_text=VALUES(signal_text),position=VALUES(position),
        close_volume=VALUES(close_volume),volume=VALUES(volume),turnover=VALUES(turnover),
        fee=VALUES(fee),trade_pnl=VALUES(trade_pnl),available=VALUES(available)"""
    batch = []; total = 0
    for path in sorted((BASE / "data" / folder).glob("*.csv")):
        name = instrument(path); position = 0
        with path.open("r", encoding="gb18030", errors="ignore", newline="") as handle:
            reader = csv.reader(handle); next(reader, None)
            for raw in reader:
                if len(raw) < 15: continue
                timestamp, equity = parse_time(raw[1]), number(raw[14])
                if timestamp is None or equity is None: continue
                signal = str(raw[3]).strip()
                if signal == "BK": position = 1
                elif signal in {"SP", "SK", "BP"}: position = 0
                batch.append((name, str(raw[2]).strip(), timestamp, number(raw[7]), equity, signal, position,
                    number(raw[8]), number(raw[9]), number(raw[10]), number(raw[11]), number(raw[12]), number(raw[13])))
                if len(batch) >= 2000:
                    cur.executemany(sql, batch); conn.commit(); total += len(batch); batch.clear()
    if batch: cur.executemany(sql, batch); conn.commit(); total += len(batch)
    cur.close(); print(f"{strategy}: imported {total:,} rows")


if __name__ == "__main__":
    ensure_schema()
    conn = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, database=DATABASE)
    for strategy, folder in STRATEGIES.items(): import_strategy(conn, strategy, folder)
    conn.close()
    # The original unified table has been replaced by per-strategy tables.
    conn = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, database=DATABASE)
    cur = conn.cursor(); cur.execute("DROP TABLE IF EXISTS strategy_equity"); conn.commit(); conn.close()
    print(f"database ready: {DATABASE}")
