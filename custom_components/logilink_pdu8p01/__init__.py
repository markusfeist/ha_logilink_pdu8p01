# Copyright 2024 Markus Feist
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""LogiLink PDU8P01 Home Assistant Integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, DEFAULT_SCAN_INTERVAL
from .pdu_api import LogiLinkPDU8P01API, PDUConnectionError

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """LogiLink PDU8P01 einrichten."""
    api = LogiLinkPDU8P01API(
        host=entry.data["host"],
        username=entry.data["username"],
        password=entry.data["password"],
    )

    coordinator = PDUDataUpdateCoordinator(hass, api, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def reload_config_service(_call) -> None:
        """Service zum Neuladen der PDU-Konfiguration (Namen & Delays)."""
        _LOGGER.info("PDU-Konfiguration wird manuell neu geladen.")
        await coordinator.async_refresh_config()

    hass.services.async_register(
        DOMAIN, "reload_config", reload_config_service
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Integration entladen."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # Service entfernen (nur wenn es der letzte Eintrag war, HA macht das meist automatisch pro Domain)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, "reload_config")
    return unload_ok


class PDUDataUpdateCoordinator(DataUpdateCoordinator):
    """Coordinator: ruft status.xml und config_PDU.htm ab."""

    def __init__(self, hass: HomeAssistant, api: LogiLinkPDU8P01API, entry: ConfigEntry) -> None:
        self.api = api
        self.entry = entry
        # Gecachte Konfiguration (Namen + Delays) – wird separat abgerufen
        self.pdu_config: dict = {
            "outlet_names": [f"Steckdose {i + 1}" for i in range(8)],
            "on_delays": [0] * 8,
            "off_delays": [0] * 8,
        }
        # Systeminformationen (MAC, Firmware, Name, Location)
        self.system_info: dict[str, str] = {
            "mac": "",
            "firmware": "",
            "name": "",
            "location": "",
        }
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )

    async def async_config_entry_first_refresh(self) -> None:
        """Beim ersten Start auch die Konfiguration laden."""
        await self._async_refresh_system_info_internal()
        await self._async_refresh_config_internal()
        await super().async_config_entry_first_refresh()

    async def async_refresh_config(self) -> None:
        """Manuelles Neuladen der Konfiguration und Benachrichtigung der Entitäten."""
        await self._async_refresh_system_info_internal()
        await self._async_refresh_config_internal()
        self.async_update_listeners()

    async def _async_refresh_system_info_internal(self) -> None:
        """MAC, Firmware und Name von info_system.htm abrufen."""
        try:
            self.system_info = await self.hass.async_add_executor_job(
                self.api.get_system_info
            )
            _LOGGER.debug("PDU-Systeminfo geladen: %s", self.system_info)
        except Exception as err:
            _LOGGER.warning("Systeminfoabfrage fehlgeschlagen: %s", err)

    async def _async_refresh_config_internal(self) -> None:
        """Namen und Delays von config_PDU.htm abrufen."""
        try:
            # noinspection PyTypeChecker
            self.pdu_config = await self.hass.async_add_executor_job(
                self.api.get_config
            )
            _LOGGER.debug("PDU-Konfiguration geladen: %s", self.pdu_config)
        except Exception as err:
            _LOGGER.warning("Konfigurationsabfrage fehlgeschlagen: %s", err)

    async def _async_update_data(self) -> dict:
        """Status von /status.xml abrufen."""
        try:
            # noinspection PyTypeChecker
            status = await self.hass.async_add_executor_job(self.api.get_status)
        except PDUConnectionError as err:
            raise UpdateFailed(f"Fehler beim Abrufen des PDU-Status: {err}") from err

        # Namen aus gecachter Konfiguration einmischen
        status["outlet_names"] = self.pdu_config.get(
            "outlet_names", [f"Steckdose {i + 1}" for i in range(8)]
        )

        # System-Infos hinzufügen
        status["pdu_system_name"] = self.system_info.get("name")
        status["pdu_firmware"] = self.system_info.get("firmware")
        status["pdu_location"] = self.system_info.get("location")

        return status
