"""
mcp_servers/time_server.py
--------------------------
A small MCP server exposing time/date/timezone tools.

Transport: stdio. Logs go to stderr only (stdout is reserved for the
MCP protocol).

Tools:
  - get_current_time(timezone)        -- current date/time in any IANA zone
  - convert_time(time, from_tz, to_tz) -- convert a time between zones
  - list_common_timezones()           -- helper for discovery

Internally we try a real API call (timeapi.io) and fall back to the
Python `zoneinfo` standard-library DB if the network is unavailable.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from typing import Optional

import requests
from mcp.server.fastmcp import FastMCP
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | time_server | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("time_server")

mcp = FastMCP("time")

TIMEAPI_URL = "https://timeapi.io/api/Time/current/zone"

# Loose-input aliases so users can say "Tokyo" instead of "Asia/Tokyo".
TZ_ALIASES = {
    "utc": "UTC", "gmt": "UTC",
    "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo", "jst": "Asia/Tokyo",
    "london": "Europe/London", "uk": "Europe/London",
    "paris": "Europe/Paris", "france": "Europe/Paris",
    "berlin": "Europe/Berlin", "germany": "Europe/Berlin",
    "new york": "America/New_York", "nyc": "America/New_York",
    "est": "America/New_York", "edt": "America/New_York",
    "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
    "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
    "chicago": "America/Chicago", "cst": "America/Chicago",
    "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
    "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
    "india": "Asia/Kolkata", "ist": "Asia/Kolkata",
    "singapore": "Asia/Singapore",
    "sydney": "Australia/Sydney", "australia": "Australia/Sydney",
    "dubai": "Asia/Dubai", "uae": "Asia/Dubai",
    "shanghai": "Asia/Shanghai", "china": "Asia/Shanghai",
    "beijing": "Asia/Shanghai",
    "hong kong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong",
    "moscow": "Europe/Moscow", "russia": "Europe/Moscow",
    "toronto": "America/Toronto", "canada": "America/Toronto",
    "sao paulo": "America/Sao_Paulo", "brazil": "America/Sao_Paulo",
}


def _normalize_tz(tz: str) -> str:
    if not tz:
        return "UTC"
    return TZ_ALIASES.get(tz.strip().lower(), tz.strip())


def _current_time_via_api(tz: str) -> Optional[dict]:
    """Try the real API call. Returns None if it fails for any reason."""
    try:
        resp = requests.get(TIMEAPI_URL, params={"timeZone": tz}, timeout=8)
        if resp.status_code != 200:
            log.warning("timeapi.io returned %d: %s", resp.status_code, resp.text[:200])
            return None
        d = resp.json()
        return {
            "timezone": d.get("timeZone", tz),
            "datetime": d.get("dateTime"),
            "date": d.get("date"),
            "time": d.get("time"),
            "day_of_week": d.get("dayOfWeek"),
            "is_daylight_saving": d.get("dstActive"),
            "source": "timeapi.io",
        }
    except requests.RequestException as exc:
        log.warning("timeapi.io unreachable: %s", exc)
        return None


def _current_time_via_zoneinfo(tz: str) -> dict:
    """Fallback using Python's stdlib zoneinfo (always works offline)."""
    try:
        now = datetime.now(ZoneInfo(tz))
    except ZoneInfoNotFoundError:
        return {"error": f"Unknown timezone: {tz!r}. Use an IANA name."}
    return {
        "timezone": tz,
        "datetime": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "utc_offset": now.strftime("%z"),
        "source": "local zoneinfo (fallback)",
    }


@mcp.tool()
def get_current_time(timezone: str = "UTC") -> dict:
    """
    Return the current date and time in the requested timezone.

    timezone -- IANA name (e.g. 'Europe/London') OR a common city/country
                name (e.g. 'Tokyo', 'India') that will be mapped to one.
                Defaults to UTC.
    """
    tz = _normalize_tz(timezone)
    log.info("get_current_time(%r) -> %s", timezone, tz)
    return _current_time_via_api(tz) or _current_time_via_zoneinfo(tz)


@mcp.tool()
def convert_time(time_str: str, from_timezone: str, to_timezone: str) -> dict:
    """
    Convert a time from one timezone to another.

    time_str       -- ISO-format time string, e.g. '2026-05-30T14:30' or '14:30'.
                      Bare 'HH:MM' is interpreted on today's date.
    from_timezone  -- source IANA timezone or common name.
    to_timezone    -- target IANA timezone or common name.
    """
    src = _normalize_tz(from_timezone)
    dst = _normalize_tz(to_timezone)
    log.info("convert_time(%r, %s -> %s)", time_str, src, dst)

    try:
        src_zi = ZoneInfo(src)
        dst_zi = ZoneInfo(dst)
    except ZoneInfoNotFoundError as exc:
        return {"error": f"Unknown timezone: {exc}"}

    # Parse the time. Accept "HH:MM", "HH:MM:SS", or full ISO.
    raw = time_str.strip()
    today = datetime.now(src_zi).date()
    try:
        if "T" in raw or " " in raw or "-" in raw[:8]:
            naive = datetime.fromisoformat(raw.replace(" ", "T"))
        else:
            # Bare HH:MM or HH:MM:SS
            parts = [int(p) for p in raw.split(":")]
            while len(parts) < 3:
                parts.append(0)
            h, m, s = parts[:3]
            naive = datetime(today.year, today.month, today.day, h, m, s)
    except (ValueError, IndexError) as exc:
        return {"error": f"Could not parse time {time_str!r}: {exc}"}

    src_dt = naive.replace(tzinfo=src_zi)
    dst_dt = src_dt.astimezone(dst_zi)

    return {
        "from": {
            "timezone": src,
            "datetime": src_dt.isoformat(timespec="seconds"),
        },
        "to": {
            "timezone": dst,
            "datetime": dst_dt.isoformat(timespec="seconds"),
            "date": dst_dt.strftime("%Y-%m-%d"),
            "time": dst_dt.strftime("%H:%M:%S"),
            "day_of_week": dst_dt.strftime("%A"),
        },
    }


@mcp.tool()
def list_common_timezones() -> dict:
    """
    Return a small curated list of common timezone aliases the server
    understands. Useful for discovery when the model is unsure what
    canonical IANA zone to pass.
    """
    log.info("list_common_timezones()")
    return {
        "count": len(TZ_ALIASES),
        "aliases": sorted(set(TZ_ALIASES.values())),
    }


if __name__ == "__main__":
    log.info("Starting Time MCP server (stdio)")
    mcp.run(transport="stdio")
