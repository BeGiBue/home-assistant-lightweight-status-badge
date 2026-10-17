"""Run custom integrations in the real HA test harness."""

from unittest.mock import AsyncMock, patch

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def offline_catalog():
    """Tests never touch the network: no online catalog, so the bundled copy is used."""
    with patch(
        "custom_components.lightweight_status_badge.catalog._fetch_online",
        new=AsyncMock(return_value=None),
    ):
        yield


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def rule_data():
    return {"id": "ups", "entity_id": "sensor.ups", "kind": "ups_status"}
