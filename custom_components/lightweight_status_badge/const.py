"""Integration constants."""

DOMAIN = "lightweight_status_badge"
PLATFORMS = ["sensor", "binary_sensor"]
MAX_RULES = 1000
PAGE_SIZE = 100
SAVE_DELAY = 1
DISPATCH_DELAY = 0.05
SIGNAL_UPDATED = f"{DOMAIN}_updated"

# Rule catalog used only while a user picks a device/integration in the options flow.
# The same file ships inside the integration (offline fallback) and is served from the
# default branch (newer entries without a new release). Never fetched at runtime.
CATALOG_URL = (
    "https://raw.githubusercontent.com/BeGiBue/home-assistant-lightweight-status-badge/"
    "main/custom_components/lightweight_status_badge/catalog.json"
)
CATALOG_TIMEOUT = 5
CATALOG_MAX_BYTES = 256 * 1024
CATALOG_TTL = 600
CATALOG_CACHE_KEY = f"{DOMAIN}_catalog_cache"
