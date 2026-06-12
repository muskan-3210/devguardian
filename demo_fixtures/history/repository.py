"""Historical data-access code — parameterised SQL, context-managed connections."""
import logging
import sqlite3
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = "inventory.db"


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        logger.exception("Database operation failed")
        raise
    finally:
        conn.close()


def get_user_by_id(user_id: int) -> dict | None:
    """Fetch a user row using a parameterised query."""
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def update_stock_level(sku: str, delta: int) -> None:
    """Adjust stock for a SKU atomically."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE inventory SET stock = stock + ? WHERE sku = ?", (delta, sku)
        )
        logger.info("Stock adjusted for %s by %+d", sku, delta)
