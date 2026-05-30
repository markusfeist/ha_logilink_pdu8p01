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
"""Sensor platform für LogiLink PDU8P01 – Strom, Temperatur, Luftfeuchtigkeit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfTemperature,
    PERCENTAGE,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import PDUDataUpdateCoordinator
from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class PDUSensorEntityDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], float | None]


SENSOR_DESCRIPTIONS: tuple[PDUSensorEntityDescription, ...] = (
    PDUSensorEntityDescription(
        key="current",
        name="Stromstärke",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:current-ac",
        value_fn=lambda d: d.get("current"),
    ),
    PDUSensorEntityDescription(
        key="temperature",
        name="Temperatur",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("temperature"),
    ),
    PDUSensorEntityDescription(
        key="humidity",
        name="Luftfeuchtigkeit",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("humidity"),
    ),
    PDUSensorEntityDescription(
        key="pdu_system_name",
        name="Systemname",
        icon="mdi:information-outline",
        value_fn=lambda d: d.get("pdu_system_name"),
    ),
    PDUSensorEntityDescription(
        key="pdu_firmware",
        name="Firmware Version",
        icon="mdi:version",
        value_fn=lambda d: d.get("pdu_firmware"),
    ),
    PDUSensorEntityDescription(
        key="pdu_location",
        name="Standort",
        icon="mdi:map-marker",
        value_fn=lambda d: d.get("pdu_location"),
    ),
)


async def async_setup_entry(
        hass: HomeAssistant,
        entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PDUDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PDUSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    )


class PDUSensor(CoordinatorEntity[PDUDataUpdateCoordinator], SensorEntity):
    entity_description: PDUSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(self, coordinator: PDUDataUpdateCoordinator, entry: ConfigEntry, description: PDUSensorEntityDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def device_info(self) -> DeviceInfo:
        # Ist halt eine HTTP-API
        # noinspection HttpUrlsUsage
        info = DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"LogiLink PDU8P01 ({self._entry.data['host']})",
            manufacturer="LogiLink",
            model="PDU8P01",
            sw_version=self.coordinator.system_info.get("firmware"),
            hw_version=None,
            configuration_url=f"http://{self._entry.data['host']}",
        )

        mac = self.coordinator.system_info.get("mac")
        if mac:
            info["connections"] = {(dr.CONNECTION_NETWORK_MAC, dr.format_mac(mac))}

        return info
