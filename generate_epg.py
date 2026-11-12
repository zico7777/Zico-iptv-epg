#!/usr/bin/env python3
"""Build a small XMLTV guide from explicitly approved M3U Edit channel IDs.

The private Zico IPTV playlist is deliberately NOT read or downloaded here.
Only public channel IDs/display names and the resulting XMLTV are published.
"""
from __future__ import annotations

import copy
import gzip
import os
import re
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_URL = "https://m3u-edit.com/epg-source.php?file={}"
SOURCES = ("AR1.xml.gz", "ES1.xml.gz")
OUTPUT = Path("epg.xml")
LOOKAHEAD_DAYS = 7

# source XMLTV channel ID -> (the exact tvg-id to publish, display name)
# These are non-sports channels only. Sports IDs are intentionally untouched
# and excluded until an exact/verified source match is available.
CHANNEL_MAP = {
    "Canal.Animal.Planet.(Argentina).ar": ("Animal Planet", "Animal Planet"),
    "Canal.AXN.(Argentina).ar": ("AXN", "AXN"),
    "Canal.Cinecanal.(Argentina).ar": ("Cinecanal", "Cinecanal"),
    "Canal.CNN.Internacional.ar": ("CNN Internacional", "CNN Internacional"),
    "Canal.Discovery.Theater.(Latinoamérica).ar": ("Discovery Theater", "Discovery Theater"),
    "Canal.Discovery.World.Latinoamérica.ar": ("Discovery World", "Discovery World"),
    "Canal.Elgourmet.ar": ("El Gourmet", "El Gourmet"),
    "Canal.Film.&.Arts.ar": ("Film&Arts", "Film & Arts"),
    "Canal.Golden.(Argentina).ar": ("Golden", "Golden"),
    "Canal.HBO.(Argentina).ar": ("HBO", "HBO"),
    "Canal.HBO.Family.Latinoamérica.ar": ("HBO Family", "HBO Family"),
    "Canal.HBO.Plus.ar": ("HBO +", "HBO Plus"),
    "Canal.HBO.Pop.ar": ("HBO POP", "HBO Pop"),
    "Canal.History.2.(Argentina).ar": ("History 2", "History 2"),
    "Canal.Lifetime.(Argentina).ar": ("Lifetime", "Lifetime"),
    "Canal.Sony.(Argentina).ar": ("Sony", "Sony Channel"),
    "Canal.Space.(Argentina).ar": ("Space", "Space"),
    "Canal.Star.Channel.(Argentina).ar": ("Star Channel", "Star Channel"),
    "Canal.TNT.(Argentina).ar": ("TNT", "TNT"),
    "Canal.Warner.TV.(Argentina).ar": ("Warner", "Warner"),
    "AMC.es": ("AMC", "AMC"),
    "Comedy.Central.HD.es": ("Comedy Central", "Comedy Central"),
    "Dark.es": ("DARK", "DARK"),
}


def parse_xmltv_time(value: str) -> datetime:
    match = re.fullmatch(r"(\d{14})(?:\s*([+-]\d{4}))?", value.strip())
    if not match:
        raise ValueError(f"Invalid XMLTV timestamp: {value!r}")
    dt = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    offset = match.group(2) or "+0000"
    sign = 1 if offset[0] == "+" else -1
    minutes = sign * (int(offset[1:3]) * 60 + int(offset[3:5]))
    return dt.replace(tzinfo=timezone(timedelta(minutes=minutes)))


def download_feed(filename: str) -> bytes:
    url = BASE_URL.format(filename)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Zico-EPG-builder/1.0 (+XMLTV aggregation)"},
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        payload = response.read()
    if payload[:2] == b"\x1f\x8b":
        payload = gzip.decompress(payload)
    return payload


def main() -> None:
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=LOOKAHEAD_DAYS)
    programmes: dict[str, dict[tuple[str, str, str], ET.Element]] = {}
    names: dict[str, str] = {}
    feed_ok = 0
    errors: list[str] = []

    for filename in SOURCES:
        try:
            payload = download_feed(filename)
            root = ET.fromstring(payload)
            feed_ok += 1
            feed_channels = {
                channel.get("id"): channel
                for channel in root.findall("channel")
                if channel.get("id") in CHANNEL_MAP
            }
            for source_id, channel in feed_channels.items():
                target_id, display_name = CHANNEL_MAP[source_id]
                # A target ID may be supplied by only one approved source ID.
                names.setdefault(target_id, display_name)

            for item in root.findall("programme"):
                source_id = item.get("channel", "")
                mapping = CHANNEL_MAP.get(source_id)
                # Require both an approved ID and its channel definition in this feed.
                if not mapping or source_id not in feed_channels:
                    continue
                target_id, display_name = mapping
                start_raw, stop_raw = item.get("start"), item.get("stop")
                if not start_raw or not stop_raw:
                    continue
                try:
                    start, stop = parse_xmltv_time(start_raw), parse_xmltv_time(stop_raw)
                except ValueError:
                    continue
                if stop <= now or start > horizon or stop <= start:
                    continue
                # Require a title, so empty/broken records never enter the guide.
                title = " ".join((item.findtext("title") or "").split())
                if not title:
                    continue
                cloned = copy.deepcopy(item)
                cloned.set("channel", target_id)
                key = (start_raw, stop_raw, title.casefold())
                programmes.setdefault(target_id, {})[key] = cloned
        except Exception as exc:  # keep other regional feeds usable
            errors.append(f"{filename}: {type(exc).__name__}: {exc}")
            print(f"WARNING: could not process {filename}: {exc}", file=sys.stderr)

    if feed_ok == 0:
        raise RuntimeError("No XMLTV source could be downloaded; existing epg.xml was not changed")

    # Only publish channels that have actual current/future programme records.
    valid = {cid: items for cid, items in programmes.items() if items}
    total = sum(len(items) for items in valid.values())
    if total == 0:
        raise RuntimeError("No valid current/future programme records found; existing epg.xml was not changed")

    tv = ET.Element("tv", {"generator-info-name": "Zico IPTV EPG", "generator-info-url": "https://github.com/zico7777/Zico-iptv-epg"})
    for channel_id in sorted(valid):
        channel = ET.SubElement(tv, "channel", {"id": channel_id})
        ET.SubElement(channel, "display-name").text = names.get(channel_id, channel_id)

    ordered = []
    for channel_id, items in valid.items():
        ordered.extend(items.values())
    ordered.sort(key=lambda p: (p.get("start", ""), p.get("channel", "")))
    for programme in ordered:
        tv.append(programme)

    ET.indent(tv, space="  ")
    xml_bytes = ET.tostring(tv, encoding="utf-8", xml_declaration=True)
    # Atomic replacement: never leave a partial XML file on disk.
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("wb", dir=OUTPUT.parent, delete=False) as tmp:
        tmp.write(xml_bytes)
        temp_name = tmp.name
    os.replace(temp_name, OUTPUT)

    counts = Counter({cid: len(items) for cid, items in valid.items()})
    print(f"SUCCESS: {len(valid)} channels, {total} programme records, window: now to {LOOKAHEAD_DAYS} days")
    for channel_id, count in sorted(counts.items()):
        print(f"  {channel_id}: {count} programmes")
    if errors:
        print("Some feeds failed; successful feeds were still used:")
        for error in errors:
            print(f"  - {error}")


if __name__ == "__main__":
    main()
