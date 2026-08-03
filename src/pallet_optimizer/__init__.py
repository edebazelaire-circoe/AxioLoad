"""AxioLoad transport loading optimizer."""

from .platform import compose_runtime
from .version import APP_VERSION

__version__ = APP_VERSION

# All legacy installers are now composed from one ordered and testable root.
compose_runtime()
