"""Real authenticated WS clients and HA permissions for global mutations."""

from datetime import timedelta

import pytest
from homeassistant.core import Context
from homeassistant.exceptions import Unauthorized
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from custom_components.lightweight_status_badge.api import mutate
from custom_components.lightweight_status_badge.const import DOMAIN
from tests.test_integration import setup_entry


async def test_two_clients_global_ack_and_revoke(hass, hass_ws_client, rule_data):
    # Set up websocket infrastructure before registering our custom commands.
    first = await hass_ws_client(hass)
    second = await hass_ws_client(hass)
    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    for client in (first, second):
        await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
        assert (await client.receive_json())["success"]
        assert (await client.receive_json())["type"] == "event"
    await first.send_json_auto_id({"type": f"{DOMAIN}/alerts", "language": "de"})
    result = (await first.receive_json())["result"]
    alert = result["alerts"][0]
    assert "Batteriebetrieb" in alert["description"]
    await first.send_json_auto_id(
        {"type": f"{DOMAIN}/acknowledge", "rule_id": "ups", "occurrence": alert["occurrence"]}
    )
    assert (await first.receive_json())["success"]
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    for client in (first, second):
        assert (await client.receive_json())["type"] == "event"
    await second.send_json_auto_id({"type": f"{DOMAIN}/alerts"})
    assert (await second.receive_json())["result"]["alerts"][0]["acknowledged"]
    await second.send_json_auto_id(
        {
            "type": f"{DOMAIN}/acknowledge",
            "rule_id": "ups",
            "occurrence": alert["occurrence"],
            "acknowledged": False,
        }
    )
    assert (await second.receive_json())["success"]
    assert entry.runtime_data.counts == (1, 1, 2)


async def test_readonly_can_read_not_mutate(
    hass, hass_ws_client, hass_read_only_access_token, rule_data
):
    client = await hass_ws_client(hass, hass_read_only_access_token)
    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    await client.send_json_auto_id({"type": f"{DOMAIN}/alerts"})
    result = await client.receive_json()
    assert result["success"]
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/acknowledge",
            "rule_id": "ups",
            "occurrence": entry.runtime_data.alerts["ups"].occurrence,
        }
    )
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"
    assert entry.runtime_data.counts == (1, 1, 2)


async def test_service_checks_caller_and_stale_occurrence(
    hass, hass_ws_client, hass_admin_user, hass_read_only_user, rule_data
):
    await hass_ws_client(hass)
    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    data = {"rule_id": "ups", "occurrence": entry.runtime_data.alerts["ups"].occurrence}
    with pytest.raises(Unauthorized):
        await hass.services.async_call(DOMAIN, "acknowledge", data, blocking=True)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "acknowledge",
            data,
            blocking=True,
            context=Context(user_id=hass_read_only_user.id),
        )
    await hass.services.async_call(
        DOMAIN, "acknowledge", data, blocking=True, context=Context(user_id=hass_admin_user.id)
    )
    assert entry.runtime_data.counts == (0, 1, 0)
    entry.runtime_data.set_acknowledged("ups", data["occurrence"], False)
    with pytest.raises(ValueError):
        mutate(entry.runtime_data, hass_admin_user, "ups", "stale", True)
    assert entry.runtime_data.counts == (1, 1, 2)


async def test_subscription_survives_options_reload(hass, hass_ws_client, rule_data):
    client = await hass_ws_client(hass)
    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]
    assert (await client.receive_json())["event"]["loaded"]
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=1))
    await hass.async_block_till_done()
    # Unload sends an invalidation, then the new core sends a loaded invalidation.
    events = [await client.receive_json(), await client.receive_json()]
    assert all(e["type"] == "event" for e in events)
    assert events[-1]["event"]["loaded"]
    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": 1})
    assert (await client.receive_json())["success"]


async def test_no_read_permission_hides_details_and_blocks_mutation(
    hass, hass_ws_client, hass_admin_user, rule_data
):
    client = await hass_ws_client(hass)
    hass_admin_user.mock_policy({"entities": {}})
    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    await client.send_json_auto_id({"type": f"{DOMAIN}/alerts"})
    response = await client.receive_json()
    assert response["success"]
    assert response["result"]["alerts"] == []
    assert response["result"]["total"] == 0
    await client.send_json_auto_id(
        {
            "type": f"{DOMAIN}/acknowledge",
            "rule_id": "ups",
            "occurrence": entry.runtime_data.alerts["ups"].occurrence,
        }
    )
    assert (await client.receive_json())["error"]["code"] == "unauthorized"


async def test_unauthenticated_command_rejected_by_ha_auth_phase(hass, rule_data):
    import json
    import logging
    from unittest.mock import AsyncMock, Mock

    from homeassistant.components.websocket_api.auth import AuthPhase
    from homeassistant.components.websocket_api.error import Disconnect

    hass.states.async_set("sensor.ups", "OB")
    entry = await setup_entry(hass, [rule_data])
    send = AsyncMock()
    phase = AuthPhase(logging.getLogger(__name__), hass, Mock(), Mock(), Mock(), send)
    with pytest.raises(Disconnect):
        await phase.async_handle(
            {
                "type": f"{DOMAIN}/acknowledge",
                "id": 1,
                "rule_id": "ups",
                "occurrence": entry.runtime_data.alerts["ups"].occurrence,
            }
        )
    send.assert_awaited_once()
    assert json.loads(send.call_args.args[0])["type"] == "auth_invalid"
    assert entry.runtime_data.counts == (1, 1, 2)
