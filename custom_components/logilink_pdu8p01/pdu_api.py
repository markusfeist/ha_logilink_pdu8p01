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
"""API client für LogiLink PDU8P01 / Intellinet 163682.

Verifizierte Endpunkte:

  GET  /status.xml        → Outlet-Zustände, Strom, Temp, Feuchte
  GET  /config_PDU.htm    → Socket-Namen, ON-Delay, OFF-Delay pro Socket
  GET  /control_outlet.htm?outlet{N}=1&op={0|1}&submit=Apply → Schalten
       op=0 = einschalten, op=1 = ausschalten
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET  # noqa: N817
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

_LOGGER = logging.getLogger(__name__)

# noinspection HttpUrlsUsage
STATUS_URL = "http://{host}/status.xml"
# noinspection HttpUrlsUsage
CONFIG_URL = "http://{host}/config_PDU.htm"
# noinspection HttpUrlsUsage
CONTROL_URL = "http://{host}/control_outlet.htm"


class PDUConnectionError(Exception):
    """Raised when communication with the PDU fails."""


class LogiLinkPDU8P01API:
    """HTTP-Client für LogiLink PDU8P01 / Intellinet 163682."""

    def __init__(
            self,
            host: str,
            username: str = "admin",
            password: str = "admin",
            timeout: int = 10,
    ) -> None:
        self.host = host
        self.auth = HTTPBasicAuth(username, password)
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Öffentliche Methoden
    # ------------------------------------------------------------------

    def get_status(self) -> dict[str, Any]:
        """Outlet-Zustände + Messwerte von /status.xml abrufen."""
        url = STATUS_URL.format(host=self.host)
        for auth in (None, self.auth):
            try:
                resp = requests.get(url, auth=auth, timeout=self.timeout)
                if resp.status_code == 200:
                    break
                if resp.status_code == 401 and auth is None:
                    continue
            except requests.RequestException as exc:
                raise PDUConnectionError(f"Statusabfrage fehlgeschlagen: {exc}") from exc

        if resp is None or resp.status_code != 200:
            raise PDUConnectionError(
                f"Statusabfrage fehlgeschlagen (HTTP {resp.status_code if resp else '?'})"
            )

        _LOGGER.debug("PDU status.xml: %s", resp.text)
        return self._parse_status(resp.text)

    def get_config(self) -> dict[str, Any]:
        """Socket-Namen und Delays von /config_PDU.htm abrufen.

        Gibt zurück:
          outlet_names  – Liste von 8 Strings
          on_delays     – Liste von 8 int (Sekunden)
          off_delays    – Liste von 8 int (Sekunden)
        """
        url = CONFIG_URL.format(host=self.host)
        try:
            resp = requests.get(url, auth=self.auth, timeout=self.timeout)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise PDUConnectionError(f"Konfigurationsabfrage fehlgeschlagen: {exc}") from exc

        _LOGGER.debug("PDU config_PDU.htm: %s", resp.text[:1000])
        return self._parse_config(resp.text)

    def set_outlet(self, outlet_index: int, state: bool) -> None:
        """Steckdose schalten.

        Verifiziertes Format:
          GET /control_outlet.htm?outlet{N}=1&op={0|1}&submit=Apply
          op=0 = einschalten, op=1 = ausschalten
        """
        if not 0 <= outlet_index <= 7:
            raise ValueError(f"Outlet-Index muss 0–7 sein, nicht {outlet_index}")

        params = {
            f"outlet{outlet_index}": "1",
            "op": "0" if state else "1",
            "submit": "Apply",
        }
        url = CONTROL_URL.format(host=self.host)
        try:
            resp = requests.get(url, params=params, auth=self.auth, timeout=self.timeout)
            _LOGGER.debug(
                "GET %s params=%s → HTTP %d  body=%s",
                url, params, resp.status_code, resp.text[:200],
            )
            if resp.status_code == 401:
                raise PDUConnectionError("Authentifizierung fehlgeschlagen (HTTP 401).")
            if resp.status_code not in (200, 204):
                raise PDUConnectionError(
                    f"Schalten fehlgeschlagen (HTTP {resp.status_code})"
                )
        except (PDUConnectionError, requests.Timeout):
            raise
        except requests.RequestException as exc:
            raise PDUConnectionError(f"Schalten fehlgeschlagen: {exc}") from exc

    # ------------------------------------------------------------------
    # Interne Parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_status(xml_text: str) -> dict[str, Any]:
        """Verifiziertes XML-Format parsen."""
        text = xml_text.strip()
        if not text.startswith("<"):
            raise PDUConnectionError(f"Kein XML: {text[:100]}")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise PDUConnectionError(f"Ungültiges XML: {exc}") from exc

        def _get(tag: str, default: str | None = None) -> str | None:
            el = root.find(tag)
            return el.text.strip() if el is not None and el.text else default

        outlets = [(_get(f"outletStat{i}", "off") or "off").lower() == "on" for i in range(8)]

        def _float(*tags: str) -> float | None:
            for tag in tags:
                val = _get(tag)
                if val is not None:
                    try:
                        return float(val)
                    except ValueError:
                        continue
            return None

        return {
            "outlets": outlets,
            "temperature": _float("tempBan", "temperature", "temp"),
            "humidity": _float("humBan", "humidity", "hum"),
            "current": _float("curBan", "current", "cur"),
        }

    @staticmethod
    def _parse_config(html: str) -> dict[str, Any]:
        """Socket-Namen und Delays aus /config_PDU.htm HTML parsen.

        Relevante Input-Felder (verifiziert):
          otlt{N}   – Socket-Name
          ondly{N}  – ON-Delay in Sekunden
          ofdly{N}  – OFF-Delay in Sekunden
        """
        outlet_names: list[str] = []
        on_delays: list[int] = []
        off_delays: list[int] = []

        for i in range(8):
            # Name
            m = re.search(
                rf'<input[^>]+name="otlt{i}"[^>]+value="([^"]*)"', html
            )
            outlet_names.append(m.group(1).strip() if m else f"Steckdose {i + 1}")

            # ON-Delay
            m = re.search(
                rf'<input[^>]+name="ondly{i}"[^>]+value="([^"]*)"', html
            )
            try:
                on_delays.append(int(m.group(1)) if m else 0)
            except ValueError:
                on_delays.append(0)

            # OFF-Delay
            m = re.search(
                rf'<input[^>]+name="ofdly{i}"[^>]+value="([^"]*)"', html
            )
            try:
                off_delays.append(int(m.group(1)) if m else 0)
            except ValueError:
                off_delays.append(0)

        _LOGGER.debug(
            "PDU config: names=%s on_delays=%s off_delays=%s",
            outlet_names, on_delays, off_delays,
        )
        return {
            "outlet_names": outlet_names,
            "on_delays": on_delays,
            "off_delays": off_delays,
        }
