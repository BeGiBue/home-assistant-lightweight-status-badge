"""Run custom integrations in the real HA test harness."""

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def rule_data():
    return {"id": "ups", "entity_id": "sensor.ups", "kind": "ups_status"}
