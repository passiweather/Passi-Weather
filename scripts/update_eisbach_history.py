#!/usr/bin/env python3
"""Load the last five days of observed Eisbach water-level readings from HND.

Writes only measured data. The existing data/eisbach.json workflow remains untouched.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
STATION = "München Himmelreichbrücke / Eisbach"
PAGE = "https://www.hnd.bayern.de/pegel/donau_bis_kelheim/muenchen-himmelreichbruecke-16515005/tabelle?days=7&methode=wasserstand&setdiskr=60"
TARGET = Path("data/eisbach-history.json")


def parse_hnd(text):
    """Extract dated stage readings from HND table HTML (German or ISO dates).

    Require the first two table cells to be timestamp and stage; no thresholds,
    fabricated interpolation, or other numeric tables enter the time series.
    """
    result = {}
    for row in re.findall(r"<tr\b[^>]*>(.*?)</tr\s*>", text, flags=re.I | re.S):
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]\s*>", row, flags=re.I | re.S)
        if len(cells) < 2:
            continue
        clean = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]*>", " ", cell))).strip() for cell in cells]
        stamp = clean[0].replace("Uhr", "").strip()
        matched = re.search(r"(\d{2}\.\d{2}\.\d{4}|\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", stamp)
        level = re.search(r"^\s*(\d{1,3}(?:[,.]\d+)?)\s*(?:cm)?\s*$", clean[1], flags=re.I)
        if not matched or not level:
            continue
        date_s, hour = matched.groups()
        fmt = "%d.%m.%Y %H:%M" if "." in date_s else "%Y-%m-%d %H:%M"
        dt = datetime.strptime(date_s + " " + hour, fmt).replace(tzinfo=TZ)
        val = float(level.group(1).replace(",", "."))
        if 0 <= val < 1000:
            result[dt.isoformat()] = val
    return result


def main():
    now = datetime.now(TZ)
    cutoff = now - timedelta(days=5)
    req = Request(PAGE, headers={"User-Agent": "Mozilla/5.0 (Passis-Wetter Pegelverlauf; GitHub Actions)"})
    with urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", "replace")
    points = parse_hnd(text)
    if TARGET.exists():
        try:
            old = json.loads(TARGET.read_text(encoding="utf-8"))
            for row in old.get("values", []):
                val = row.get("water_level_cm")
                if isinstance(val, (float, int)):
                    points.setdefault(row.get("time", ""), float(val))
        except (OSError, ValueError, TypeError):
            pass
    kept = []
    for stamp, val in points.items():
        try:
            dt = datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        if cutoff <= dt <= now + timedelta(minutes=10):
            kept.append({"time": dt.isoformat(), "water_level_cm": val})
    kept.sort(key=lambda p: p["time"])
    if len(kept) < 8:
        raise RuntimeError("Zu wenig HND-Messwerte; Datei bleibt unverändert (keine Beispieldaten)")
    payload = {"station": STATION, "source": PAGE, "updated_at": datetime.now(timezone.utc).isoformat(), "values": kept}
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Eisbach-Verlauf aktualisiert: {len(kept)} Einzelmesswerte")


if __name__ == "__main__":
    main()
