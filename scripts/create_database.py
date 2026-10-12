"""Create the configured MySQL database and one table per strategy."""
import os
import sys
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
TABLES = ("ranking_buyhold", "ranking_sar", "ranking_macd")


def create_database():
    if not DATABASE.replace("_", "").isalnum():
        raise ValueError("MYSQL_DATABASE must contain only letters, digits, and underscores")
    connection = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD)
    try:
        cursor = connection.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        connection.commit()
    finally:
        connection.close()

    connection = mysql.connector.connect(host=HOST, port=PORT, user=USER, password=PASSWORD, database=DATABASE)
    try:
        cursor = connection.cursor()
        template = (BASE / "db" / "schema.sql").read_text(encoding="utf-8")
        for table in TABLES:
            cursor.execute(template.replace("{table_name}", table))
        connection.commit()
    finally:
        connection.close()
    print(f"Database and schema are ready: {DATABASE}")


if __name__ == "__main__":
    create_database()
