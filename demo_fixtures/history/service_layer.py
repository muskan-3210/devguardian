"""Representative historical code — establishes the team's DNA:
snake_case naming, type hints, docstrings, logging module, specific exceptions.
"""
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class OrderItem:
    sku: str
    quantity: int
    unit_price_cents: int


def calculate_order_total(items: list[OrderItem]) -> int:
    """Total order value in cents, validating quantities."""
    total = 0
    for item in items:
        if item.quantity <= 0:
            raise ValueError(f"Invalid quantity for {item.sku}")
        total += item.quantity * item.unit_price_cents
    logger.debug("Order total calculated: %d cents", total)
    return total


def apply_discount(total_cents: int, percent: float) -> int:
    """Apply a percentage discount, clamped to 0-100."""
    clamped = max(0.0, min(100.0, percent))
    discounted = round(total_cents * (1 - clamped / 100))
    logger.info("Discount %.1f%% applied: %d -> %d", clamped, total_cents, discounted)
    return discounted


def fetch_inventory_level(sku: str, repository) -> int:
    """Read current stock for a SKU from the repository layer."""
    try:
        return repository.get_stock(sku)
    except KeyError:
        logger.warning("Unknown SKU requested: %s", sku)
        return 0
