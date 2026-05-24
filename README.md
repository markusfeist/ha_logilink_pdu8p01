# LogiLink PDU8P01 – Home Assistant Custom Integration

Eine native Home Assistant Integration für die **LogiLink PDU8P01** (8-Port IP-Steckdosenleiste) und die baugleiche **Intellinet 163682**.

Dieses Modul ist eine Portierung des [FHEM-Moduls](https://github.com/markusfeist/FhemLogiLinkPDU8P01) auf Home Assistant.

---

## Funktionen

| Funktion             | Beschreibung                                       |
|----------------------|----------------------------------------------------|
| 8× Schalter          | Jede Steckdose als eigene `switch`-Entität         |
| Steckdosennamen      | Werden direkt von der PDU gelesen                  |
| Stromstärke (A)      | `sensor` – Gesamtstrom                             |
| Temperatur (°C)      | `sensor` – eingebauter Sensor                      |
| Luftfeuchtigkeit (%) | `sensor` – eingebauter Sensor                      |
| Konfigurations-UI    | Einrichtung über HA-Oberfläche (kein YAML)         |
| Abfrageintervall     | Über Optionen einstellbar (5–300 s, Standard 30 s) |

---

## Installation

### Manuell (ohne HACS)

1. Diesen Ordner `logilink_pdu8p01` nach `<config>/custom_components/` kopieren.
2. Home Assistant neu starten.
3. In HA: **Einstellungen → Geräte & Dienste → Integration hinzufügen** → *LogiLink PDU8P01* suchen.
4. IP-Adresse, Benutzername (`admin`) und Passwort (`admin`) eingeben.

### Mit HACS

1. HACS öffnen → **Integrationen** → Drei-Punkte-Menü → **Benutzerdefinierte Repositories**.
2. URL des Repositories einfügen, Typ *Integration* wählen.
3. Integration in HACS installieren und HA neu starten.

---

## Konfiguration

Die Einrichtung erfolgt vollständig über die UI. Optional kann das Abfrageintervall unter **Einstellungen → Geräte & Dienste → LogiLink PDU8P01 → Optionen** angepasst werden.

---

## Services

Die Integration stellt folgende Dienste zur Verfügung:

### `logilink_pdu8p01.reload_config`
Lädt die Konfiguration (Steckdosennamen und Ein-/Ausschaltverzögerungen) direkt von der PDU neu. Dies ist nützlich, wenn Namen auf der Web-Oberfläche der PDU geändert wurden, ohne die Integration neu zu starten.

---

## Technische Details / PDU-API

Die PDU kommuniziert über HTTP:

| Endpunkt              | Methode | Beschreibung                                                          |
|-----------------------|---------|-----------------------------------------------------------------------|
| `/status.xml`         | `GET`   | Liest Outlet-Zustände, Namen, Strom, Temp, Feuchte                    |
| `/control_outlet.htm` | `POST`  | Schaltet einzelne Outlets (`outlet0`…`outlet7` = `0`/`1`)             |
| `/config_PDU.htm`     | `GET`   | Liest die Konfiguration zu den Schaltern beim Start von Homeassistant |

Authentifizierung: HTTP Basic Auth (Standard: `admin` / `admin`).

**Hinweis:** Der Status ist ohne Passwort abrufbar, das Schalten erfordert jedoch Authentifizierung.

---

## Kompatible Geräte

- LogiLink PDU8P01 (habe ich)
- Intellinet 163682 (baugleich)
- Ggf. Weitere HTTP/XML-basierte PDUs desselben OEM-Herstellers

---

## Lizenz

Analog zu Homeassistant veröffentliche ich dieses Projekt unter der Apache 2.0, siehe [LICENSE](LICENSE).
