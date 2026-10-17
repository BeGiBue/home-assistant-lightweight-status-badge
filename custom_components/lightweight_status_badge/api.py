"""Authenticated WebSocket detail channel and permission-checked global actions."""

from typing import Any

import voluptuous as vol
from homeassistant.auth.models import User
from homeassistant.auth.permissions.const import POLICY_CONTROL, POLICY_READ
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_UPDATED
from .coordinator import Coordinator


def coordinator(hass: HomeAssistant) -> Coordinator:
    for entry in hass.config_entries.async_entries(DOMAIN):
        if runtime := getattr(entry, "runtime_data", None):
            if not runtime.closed:
                return runtime
    raise HomeAssistantError("Integration not loaded")


def can_read(user: User | None, entity_id: str) -> bool:
    return (
        user is not None
        and user.is_active
        and user.permissions.check_entity(entity_id, POLICY_READ)
    )


def mutate(
    core: Coordinator,
    user: User | None,
    rule_id: str,
    occurrence: str,
    acknowledged: bool,
) -> None:
    if user is None or not user.is_active:
        raise Unauthorized()
    alert = core.alerts.get(rule_id)
    if alert is None:
        raise ValueError("Alert no longer active")
    entity_id = alert.rule.entity_id
    if not can_read(user, entity_id) or not user.permissions.check_entity(
        entity_id, POLICY_CONTROL
    ):
        raise Unauthorized(entity_id=entity_id)
    core.set_acknowledged(rule_id, occurrence, acknowledged)


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/alerts",
        vol.Optional("offset", default=0): vol.All(int, vol.Range(min=0)),
        vol.Optional("language"): vol.In(["en", "de"]),
    }
)
@callback
def ws_alerts(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        core = coordinator(hass)
        connection.send_result(
            msg["id"],
            core.details(
                msg.get("language", hass.config.language),
                msg["offset"],
                lambda entity: can_read(connection.user, entity),
            ),
        )
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        coordinator(hass)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], "not_loaded", str(err))
        return

    @callback
    def changed() -> None:
        # Invalidation only: bounded message, no state data leaks, no polling required.
        try:
            core = coordinator(hass)
        except HomeAssistantError:
            connection.send_event(msg["id"], {"loaded": False})
        else:
            connection.send_event(msg["id"], {"loaded": True, "revision": core.revision})

    connection.subscriptions[msg["id"]] = async_dispatcher_connect(hass, SIGNAL_UPDATED, changed)
    connection.send_result(msg["id"])
    changed()


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/acknowledge",
        vol.Required("rule_id"): str,
        vol.Required("occurrence"): str,
        vol.Optional("acknowledged", default=True): bool,
    }
)
@callback
def ws_acknowledge(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    try:
        mutate(
            coordinator(hass),
            connection.user,
            msg["rule_id"],
            msg["occurrence"],
            msg["acknowledged"],
        )
    except Unauthorized:
        connection.send_error(msg["id"], "unauthorized", "Entity control permission required")
    except (ValueError, HomeAssistantError) as err:
        connection.send_error(msg["id"], "invalid_alert", str(err))
    else:
        connection.send_result(msg["id"])


def async_register(hass: HomeAssistant) -> None:
    for handler in (ws_alerts, ws_subscribe, ws_acknowledge):
        websocket_api.async_register_command(hass, handler)

    async def acknowledge(call: ServiceCall) -> None:
        # Look up the authenticated caller through HA; never trust a supplied user field.
        user = (
            await hass.auth.async_get_user(call.context.user_id) if call.context.user_id else None
        )
        try:
            mutate(
                coordinator(hass),
                user,
                call.data["rule_id"],
                call.data["occurrence"],
                call.data["acknowledged"],
            )
        except ValueError as err:
            raise HomeAssistantError(str(err)) from err

    hass.services.async_register(
        DOMAIN,
        "acknowledge",
        acknowledge,
        schema=vol.Schema(
            {
                vol.Required("rule_id"): str,
                vol.Required("occurrence"): str,
                vol.Optional("acknowledged", default=True): bool,
            }
        ),
    )
