"""Price transformation: strip Dutch VAT, apply export markup."""

from config.settings import VAT_RATE, MARKUP


def net_price(original: float) -> float:
    """Remove Dutch BTW (21%) from retail price."""
    return original / VAT_RATE


def export_price(original: float) -> float:
    """Net price with export markup applied."""
    return net_price(original) * MARKUP


def format_price(value: float) -> str:
    return f"{value:.2f}"
