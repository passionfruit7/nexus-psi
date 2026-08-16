from pathlib import Path
import sqlite3


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = PROJECT_ROOT / "data"
DATABASE_PATH = DATA_DIR / "nexus.db"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect() -> sqlite3.Connection:
    """
    Open a connection to the NEXUS SQLite database.
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(
        DATABASE_PATH,
        timeout=30,
        isolation_level=None,
    )

    connection.row_factory = sqlite3.Row

    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")

    return connection


def initialize() -> None:
    """
    Create the database and all required tables.
    """

    connection = connect()

    try:
        schema = SCHEMA_PATH.read_text(encoding="utf-8")
        connection.executescript(schema)
    finally:
        connection.close()


if __name__ == "__main__":
    initialize()

    print("NEXUS database initialized at:")
    print(DATABASE_PATH)