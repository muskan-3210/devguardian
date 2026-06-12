"""Historical API layer — typed handlers, structured errors, env-based config."""
import logging
import os

logger = logging.getLogger(__name__)

SERVICE_TOKEN = os.getenv("SERVICE_TOKEN", "")


def validate_request_payload(payload: dict, required_fields: list[str]) -> list[str]:
    """Return a list of missing field names (empty when valid)."""
    missing = [field for field in required_fields if field not in payload]
    if missing:
        logger.warning("Payload rejected, missing fields: %s", missing)
    return missing


def build_error_response(status_code: int, message: str) -> dict:
    """Uniform error envelope used by every endpoint."""
    return {"error": {"code": status_code, "message": message}}


def paginate_results(items: list, page: int, page_size: int = 25) -> dict:
    """Standard pagination envelope."""
    if page < 1:
        raise ValueError("page must be >= 1")
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "page": page,
        "total": len(items),
        "has_more": start + page_size < len(items),
    }
