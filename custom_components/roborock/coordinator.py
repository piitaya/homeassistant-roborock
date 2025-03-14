"""Coordinatory for Roborock devices."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from roborock.api import RoborockClient
from roborock.cloud_api import RoborockMqttClient
from roborock.containers import MultiMapsList, HomeDataRoom
from roborock.exceptions import RoborockException

from .const import DOMAIN
from .roborock_typing import RoborockHassDeviceInfo

SCAN_INTERVAL = timedelta(seconds=30)

_LOGGER = logging.getLogger(__name__)


class RoborockDataUpdateCoordinator(
    DataUpdateCoordinator[RoborockHassDeviceInfo]
):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: RoborockClient,
        map_client: RoborockMqttClient,
        device_info: RoborockHassDeviceInfo,
        rooms: list[HomeDataRoom]
    ) -> None:
        """Initialize."""
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = client
        self.map_api = map_client
        self.devices_maps: dict[str, MultiMapsList] = {}
        self.device_info = device_info
        self.rooms = rooms

    def schedule_refresh(self) -> None:
        """Schedule coordinator refresh after 1 second."""
        self.hass.loop.call_later(1, lambda: asyncio.create_task(self.async_refresh()))

    async def release(self) -> None:
        """Disconnect from API."""
        await self.api.async_disconnect()
        if self.api != self.map_api:
            await self.map_api.async_disconnect()

    async def fill_room_mapping(self, device_info: RoborockHassDeviceInfo) -> None:
        """Builds the room mapping - only works for local api."""
        if device_info.room_mapping is None:
            room_mapping = await self.api.get_room_mapping()
            if room_mapping:
                room_iot_name = {str(room.id): room.name for room in self.rooms}
                device_info.room_mapping = {rm.segment_id: room_iot_name.get(str(rm.iot_id)) for rm in room_mapping}

    async def fill_device_multi_maps_list(self, device_info: RoborockHassDeviceInfo) -> None:
        """Get multi maps list."""
        if device_info.map_mapping is None:
            multi_maps_list = await self.api.get_multi_maps_list()
            if multi_maps_list:
                map_mapping = {map_info.mapFlag: map_info.name for map_info in multi_maps_list.map_info}
                device_info.map_mapping = map_mapping

    async def fill_device_prop(self, device_info: RoborockHassDeviceInfo) -> None:
        """Get device properties."""
        device_prop = await self.api.get_prop()
        if device_prop:
            if device_info.props:
                device_info.props.update(device_prop)
            else:
                device_info.props = device_prop

    async def fill_device_info(self, device_info: RoborockHassDeviceInfo):
        await asyncio.gather(
            *([
                self.fill_device_prop(device_info),
                self.fill_device_multi_maps_list(device_info),
                self.fill_room_mapping(device_info)
            ])
        )

    async def _async_update_data(self) -> RoborockHassDeviceInfo:
        """Update data via library."""
        try:
            await self.fill_device_info(self.device_info)
        except RoborockException as ex:
            raise UpdateFailed(ex) from ex
        return self.device_info
