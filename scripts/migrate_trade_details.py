"""Add WT8 trade detail fields to existing MySQL rows without truncating tables."""
import csv
import sys
from pathlib import Path

import mysql.connector

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
from config import settings
from scripts.import_mysql import STRATEGIES, TABLES, ensure_schema, number, parse_time, instrument


def migrate():
    ensure_schema()
    conn = mysql.connector.connect(host=settings.mysql_host, port=settings.mysql_port,
        user=settings.mysql_user, password=settings.mysql_password, database=settings.mysql_database)
    update_sql = """UPDATE {table} SET close_volume=%s,volume=%s,turnover=%s,fee=%s,
        trade_pnl=%s,available=%s WHERE instrument=%s AND timestamp=%s"""
    total = 0
    try:
        cur = conn.cursor()
        for strategy, folder in STRATEGIES.items():
            table = TABLES[strategy]
            sql = update_sql.format(table=table)
            batch = []
            for path in sorted((BASE / "data" / folder).glob("*.csv")):
                name = instrument(path)
                with path.open("r", encoding="gb18030", errors="ignore", newline="") as handle:
                    reader = csv.reader(handle)
                    next(reader, None)
                    for raw in reader:
                        if len(raw) < 15:
                            continue
                        timestamp = parse_time(raw[1])
                        if timestamp is None:
                            continue
                        batch.append((number(raw[8]), number(raw[9]), number(raw[10]),
                            number(raw[11]), number(raw[12]), number(raw[13]), name, timestamp))
                        if len(batch) >= 2000:
                            cur.executemany(sql, batch)
                            conn.commit()
                            total += len(batch)
                            batch.clear()
            if batch:
                cur.executemany(sql, batch)
                conn.commit()
                total += len(batch)
            print(f"{strategy}: trade details synchronized")
        cur.close()
    finally:
        conn.close()
    print(f"completed without truncating tables; processed {total:,} source rows")


if __name__ == "__main__":
    migrate()
