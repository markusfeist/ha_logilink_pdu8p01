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
"""Switch platform für LogiLink PDU8P01 – eine Switch-Entität pro Steckdose."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PDUDataUpdateCoordinator
from .const import DOMAIN
from .pdu_api import PDUConnectionError

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PDUDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PDUOutletSwitch(coordinator, entry, i) for i in range(8)
    )


class PDUOutletSwitch(CoordinatorEntity[PDUDataUpdateCoordinator], SwitchEntity):
    """Eine PDU-Steckdose als HA-Switch.

    Verwendet den per Socket konfigurierten ON- bzw. OFF-Delay der PDU,
    um den optimistischen Zustand so lange zu halten, bis die PDU tatsächlich
    geschaltet hat – danach wird der echte Status abgerufen.
    """

    _attr_has_entity_name = True
    _attr_device_class = SwitchDeviceClass.OUTLET

    def __init__(
        self,
        coordinator: PDUDataUpdateCoordinator,
        entry: ConfigEntry,
        outlet_index: int,
    ) -> None:
        super().__init__(coordinator)
        self._outlet_index = outlet_index
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_outlet_{outlet_index}"
        self._attr_name = None  # Verwendet Name vom Device + Index/Config
        self._optimistic_state: bool | None = None

    # ------------------------------------------------------------------
    # Eigenschaften
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        names = self.coordinator.pdu_config.get("outlet_names", [])
        if self._outlet_index < len(names):
            n = names[self._outlet_index]
            if n and n.strip():
                return n.strip()
        return f"Steckdose {self._outlet_index + 1}"

    @property
    def is_on(self) -> bool | None:
        if self._optimistic_state is not None:
            return self._optimistic_state
        if not self.coordinator.data:
            return None
        outlets = self.coordinator.data.get("outlets", [])
        if self._outlet_index < len(outlets):
            return outlets[self._outlet_index]
        return None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self.coordinator.data is not None

    @property
    def _on_delay(self) -> int:
        """ON-Delay dieser Steckdose laut PDU-Konfiguration."""
        delays = self.coordinator.pdu_config.get("on_delays", [])
        if self._outlet_index < len(delays):
            return delays[self._outlet_index]
        return 0

    @property
    def _off_delay(self) -> int:
        """OFF-Delay dieser Steckdose laut PDU-Konfiguration."""
        delays = self.coordinator.pdu_config.get("off_delays", [])
        if self._outlet_index < len(delays):
            return delays[self._outlet_index]
        return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Delays als Attribute anzeigen (sichtbar in HA)."""
        return {
            "on_delay_s":  self._on_delay,
            "off_delay_s": self._off_delay,
        }

    @property
    def device_info(self) -> DeviceInfo:
        # Ist halt eine HTTP-API
        # noinspection HttpUrlsUsage
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"LogiLink PDU8P01 ({self._entry.data['host']})",
            manufacturer="LogiLink",
            model="PDU8P01",
            configuration_url=f"http://{self._entry.data['host']}",
        )

    # ------------------------------------------------------------------
    # Schalt-Aktionen
    # ------------------------------------------------------------------

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_set_outlet(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_set_outlet(False)

    async def _async_set_outlet(self, state: bool) -> None:
        """Schalten mit optimistischem Zustand + PDU-seitigem Delay."""
        try:
            await self.hass.async_add_executor_job(
                self.coordinator.api.set_outlet, self._outlet_index, state
            )
        except PDUConnectionError as err:
            _LOGGER.error(
                "Steckdose %d (%s) konnte nicht %s werden: %s",
                self._outlet_index, self.name,
                "eingeschaltet" if state else "ausgeschaltet", err,
            )
            return

        # Optimistischen Zustand sofort setzen
        self._optimistic_state = state
        self.async_write_ha_state()

        # Delay aus PDU-Konfiguration abwarten
        delay = self._on_delay if state else self._off_delay
        if delay > 0:
            _LOGGER.debug(
                "Steckdose %d: warte %ds (%s-Delay) vor Status-Refresh.",
                self._outlet_index, delay, "ON" if state else "OFF",
            )
            await asyncio.sleep(delay)

        # Echten Zustand von der PDU abrufen
        self._optimistic_state = None
        await self.coordinator.async_request_refresh()
