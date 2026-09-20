import sqlite3
import pandas as pd
import numpy as np
import json

def analyze():
    conn = sqlite3.connect('backend/trading_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [t[0] for t in cursor.fetchall()]
    print("Tables in DB:", tables)

    # Inspect tables schema and data
    for t in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {t}")
        cnt = cursor.fetchone()[0]
        print(f"Table '{t}': {cnt} rows")

    # Let's read orders or positions
    df_orders = pd.read_sql_query("SELECT * FROM orders", conn)
    print("\n--- ORDERS SUMMARY ---")
    print(df_orders.info())
    print(df_orders.head(5))

    # Check unique symbols and amounts
    if 'symbol' in df_orders.columns:
        print("\nSymbols traded:")
        print(df_orders['symbol'].value_counts())
    
    if 'status' in df_orders.columns:
        print("\nOrder Statuses:")
        print(df_orders['status'].value_counts())

    if 'amount' in df_orders.columns:
        print("\nAmount Distribution:")
        print(df_orders['amount'].describe())

    # Check if there are other tables like trades or logs
    if 'reconciliation_logs' in tables:
        df_rec = pd.read_sql_query("SELECT * FROM reconciliation_logs", conn)
        print("\nReconciliations count:", len(df_rec))

    conn.close()

if __name__ == "__main__":
    analyze()
