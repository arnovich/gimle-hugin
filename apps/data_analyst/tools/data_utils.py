"""Shared utilities for data analyst tools."""

import os
import sqlite3
from typing import List, Optional, Tuple

import pandas as pd


def load_dataframe(
    data_source: str,
    table_name: Optional[str] = None,
) -> Tuple[pd.DataFrame, str]:
    """
    Load data from a file into a pandas DataFrame.

    Args:
        data_source: Path to CSV file or SQLite database
        table_name: Table name (required for SQLite databases with multiple tables)

    Returns:
        Tuple of (DataFrame, inferred_table_name)

    Raises:
        ValueError: If table_name is required but not provided
        FileNotFoundError: If data_source doesn't exist
    """
    if not os.path.exists(data_source):
        raise FileNotFoundError(f"Data source not found: {data_source}")

    if data_source.endswith(".csv"):
        df = pd.read_csv(data_source)
        inferred_table = os.path.basename(data_source).replace(".csv", "")
        return df, inferred_table

    elif data_source.endswith((".db", ".sqlite")):
        if not table_name:
            # List available tables to help user
            tables = list_tables(data_source)
            if len(tables) == 1:
                # Auto-select if only one table
                table_name = tables[0]
            else:
                raise ValueError(
                    f"table_name required for SQLite database. "
                    f"Available tables: {tables}"
                )
        conn = sqlite3.connect(data_source)
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        conn.close()
        return df, table_name

    else:
        # Try as SQLite database
        conn = sqlite3.connect(data_source)
        if not table_name:
            tables = list_tables(data_source)
            if len(tables) == 1:
                table_name = tables[0]
            else:
                conn.close()
                raise ValueError(
                    f"table_name required. Available tables: {tables}"
                )
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        conn.close()
        return df, table_name


def get_connection(data_source: str) -> Tuple[sqlite3.Connection, str]:
    """
    Get a SQLite connection for a data source.

    For CSV files, loads data into an in-memory SQLite database.

    Args:
        data_source: Path to CSV file or SQLite database

    Returns:
        Tuple of (connection, table_name)
    """
    if data_source.endswith(".csv"):
        conn = sqlite3.connect(":memory:")
        table_name = os.path.basename(data_source).replace(".csv", "")
        df = pd.read_csv(data_source)
        df.to_sql(table_name, conn, if_exists="replace", index=False)
        return conn, table_name

    elif data_source.endswith((".db", ".sqlite")):
        conn = sqlite3.connect(data_source)
        return conn, ""

    else:
        # Try as SQLite database
        conn = sqlite3.connect(data_source)
        return conn, ""


def list_tables(data_source: str) -> List[str]:
    """
    List all tables in a SQLite database.

    Args:
        data_source: Path to SQLite database

    Returns:
        List of table names
    """
    conn = sqlite3.connect(data_source)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()
    return tables
