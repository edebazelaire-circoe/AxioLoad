"""AxioLoad transport loading optimizer."""

from .admin_panel import install_admin_panel_injection
from .scaling import install_unlimited_item_count

__version__ = "0.12.0"

install_unlimited_item_count()
install_admin_panel_injection()
