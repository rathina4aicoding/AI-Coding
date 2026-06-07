"""
LLM_Call_Stage0_sdk_with_tools.py
---------------------------------
Stage 0 (single Claude call) -> Stage 0 + Tool Use.

When the user asks something the model can't know on its own - "what time
is it in Tokyo?" or "what's the weather in Mumbai?" - Claude returns a
`tool_use` block instead of a final answer. We execute the matching
Python function, hand the result back as a `tool_result` block, and loop
until Claude is ready to reply in plain text.

Two tools are exposed:

  1. get_current_time(timezone)
     Returns the current date+time in any IANA timezone (e.g.
     "Asia/Tokyo", "America/New_York", "UTC").
     Tries timeapi.io first (real API call as requested); falls back to
     Python's built-in zoneinfo database if the network is unavailable.
     Either way the answer is accurate to the second.

  2. get_current_weather(city, country=None)
     Returns the current weather for any city in the world.
     Uses two real public APIs (no key needed):
       - Open-Meteo geocoding API: city name -> lat/lon
       - Open-Meteo forecast API: lat/lon -> current conditions

Both APIs are free, key-less, and rate-limit-friendly for demo use.
Production code should add retries, caching, and a User-Agent header.

Install:  pip install anthropic gradio python-dotenv requests
Run:      python LLM_Call_Stage0_sdk_with_tools.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import gradio as gr
import requests
from anthropic import Anthropic, APIError
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
load_dotenv(override=False)

API_KEY = os.getenv("CLAUDE_API_KEY")
if not API_KEY:
    sys.stderr.write(
        "ERROR: CLAUDE_API_KEY not found. Create a .env file containing:\n"
        "  CLAUDE_API_KEY=sk-ant-...\n"
    )
    sys.exit(1)

# Valid IDs: claude-haiku-4-5, claude-sonnet-4-6, claude-opus-4-6, claude-opus-4-7
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

# Safety cap on how many times Claude can call a tool in a single user turn.
# Stops a misbehaving loop where the model keeps calling tools forever.
MAX_TOOL_ITERATIONS = 5

client = Anthropic(api_key=API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)-18s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("stage0.tools")

SYSTEM_PROMPT = (
    "You are a friendly, concise assistant. You have access to two tools:\n"
    "  - get_current_time: for any question about the current date/time in "
    "a specific timezone, city, or country.\n"
    "  - get_current_weather: for any question about the current weather "
    "in a specific city.\n"
    "\n"
    "When the user asks about current date/time or current weather, you "
    "MUST call the appropriate tool rather than guessing. After the tool "
    "returns, summarize the answer naturally in plain English - do not "
    "dump raw JSON at the user. For any other questions, answer normally "
    "without calling tools."
)


# ===========================================================================
# Tool 1: Current time
# ===========================================================================
# We use a real API call (timeapi.io) per the requirement, with a graceful
# fallback to Python's zoneinfo so the demo still works offline or if the
# API is down. This is also a good teaching point: production tools should
# always have a sensible degradation path.

TIMEAPI_URL = "https://timeapi.io/api/Time/current/zone"


def _normalize_timezone(tz: str) -> str:
    """
    Accept loose inputs like 'tokyo', 'new york', 'IST', 'london' and map
    them to canonical IANA timezone strings. Best-effort - if no match we
    return the input as-is and let the downstream call surface the error.
    """
    if not tz:
        return "UTC"
    raw = tz.strip()
    # Common shortcuts and city names users might say.
    aliases = {
        "utc": "UTC", "gmt": "UTC",
        "tokyo": "Asia/Tokyo", "japan": "Asia/Tokyo", "jst": "Asia/Tokyo",
        "london": "Europe/London", "uk": "Europe/London", "bst": "Europe/London",
        "paris": "Europe/Paris", "france": "Europe/Paris", "cet": "Europe/Paris",
        "berlin": "Europe/Berlin", "germany": "Europe/Berlin",
        "new york": "America/New_York", "nyc": "America/New_York",
        "est": "America/New_York", "edt": "America/New_York",
        "los angeles": "America/Los_Angeles", "la": "America/Los_Angeles",
        "pst": "America/Los_Angeles", "pdt": "America/Los_Angeles",
        "chicago": "America/Chicago", "cst": "America/Chicago",
        "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
        "bangalore": "Asia/Kolkata", "bengaluru": "Asia/Kolkata",
        "india": "Asia/Kolkata", "ist": "Asia/Kolkata",
        "singapore": "Asia/Singapore", "sgt": "Asia/Singapore",
        "sydney": "Australia/Sydney", "australia": "Australia/Sydney",
        "dubai": "Asia/Dubai", "uae": "Asia/Dubai",
        "shanghai": "Asia/Shanghai", "china": "Asia/Shanghai",
        "beijing": "Asia/Shanghai",
        "hong kong": "Asia/Hong_Kong", "hk": "Asia/Hong_Kong",
        "moscow": "Europe/Moscow", "russia": "Europe/Moscow",
        "sao paulo": "America/Sao_Paulo", "brazil": "America/Sao_Paulo",
        "toronto": "America/Toronto", "canada": "America/Toronto",
    }
    return aliases.get(raw.lower(), raw)


def get_current_time(timezone: str = "UTC") -> dict:
    """
    Return the current date/time in the requested IANA timezone.

    Strategy:
      1. Normalize loose inputs ('tokyo' -> 'Asia/Tokyo').
      2. Try a real API call to timeapi.io.
      3. Fall back to Python's local zoneinfo if the API is unreachable.
    """
    tz = _normalize_timezone(timezone)
    log.info("tool: get_current_time(timezone=%r)", tz)

    # --- Attempt the API call ---
    try:
        resp = requests.get(TIMEAPI_URL, params={"timeZone": tz}, timeout=8)
        if resp.status_code == 200:
            data = resp.json()
            return {
                "timezone": data.get("timeZone", tz),
                "datetime": data.get("dateTime"),
                "date": data.get("date"),
                "time": data.get("time"),
                "day_of_week": data.get("dayOfWeek"),
                "is_daylight_saving": data.get("dstActive"),
                "source": "timeapi.io",
            }
        # timeapi.io returns 400 on unknown zones; surface the message
        if resp.status_code == 400:
            log.warning("timeapi.io rejected timezone %r: %s",
                        tz, resp.text[:200])
    except requests.RequestException as exc:
        log.warning("timeapi.io unreachable (%s); falling back to local zoneinfo", exc)

    # --- Fallback: local IANA timezone DB shipped with Python ---
    try:
        now = datetime.now(ZoneInfo(tz))
    except ZoneInfoNotFoundError:
        return {
            "error": (
                f"Unknown timezone: {timezone!r}. Use an IANA name like "
                f"'Europe/London' or 'Asia/Tokyo'."
            ),
        }
    return {
        "timezone": tz,
        "datetime": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "day_of_week": now.strftime("%A"),
        "utc_offset": now.strftime("%z"),
        "source": "local zoneinfo (fallback)",
    }


# ===========================================================================
# Tool 2: Current weather
# ===========================================================================
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Open-Meteo weather codes -> human descriptions
# Reference: https://open-meteo.com/en/docs#weather_variable_documentation
_WMO_DESCRIPTIONS = {
    0:  "clear sky",
    1:  "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "depositing rime fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "light snowfall", 73: "moderate snowfall", 75: "heavy snowfall",
    77: "snow grains",
    80: "light rain showers", 81: "moderate rain showers",
    82: "violent rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with light hail", 99: "thunderstorm with heavy hail",
}


def get_current_weather(city: str, country: str | None = None) -> dict:
    """
    Look up the current weather for a city anywhere in the world.

    Step 1: city (+ optional country) -> latitude/longitude via Open-Meteo
            geocoding API.
    Step 2: lat/lon -> current weather via Open-Meteo forecast API.
    """
    if not city or not city.strip():
        return {"error": "city is required"}

    log.info("tool: get_current_weather(city=%r, country=%r)", city, country)

    # --- Step 1: Geocoding ---
    try:
        geo_resp = requests.get(
            GEOCODE_URL,
            params={"name": city.strip(), "count": 5, "language": "en", "format": "json"},
            timeout=8,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
    except requests.RequestException as exc:
        return {"error": f"Geocoding request failed: {exc}"}
    except ValueError:
        return {"error": "Geocoding returned a non-JSON response."}

    results = geo_data.get("results") or []
    if not results:
        return {
            "error": f"No location found for city={city!r}"
                     + (f", country={country!r}" if country else ""),
        }

    # If a country was specified, filter for matches (by name OR ISO code).
    if country:
        ctry = country.strip().lower()
        filtered = [
            r for r in results
            if (r.get("country", "").lower() == ctry
                or r.get("country_code", "").lower() == ctry)
        ]
        if filtered:
            results = filtered

    # Pick the first match (the API returns by population, so this is the
    # most likely city someone means when they say "London").
    place = results[0]
    lat = place.get("latitude")
    lon = place.get("longitude")
    resolved_name = place.get("name")
    resolved_country = place.get("country")
    resolved_admin = place.get("admin1")  # e.g. state/region

    if lat is None or lon is None:
        return {"error": f"Geocoding result missing coordinates: {place}"}

    # --- Step 2: Current weather ---
    try:
        wx_resp = requests.get(
            FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current": (
                    "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "weather_code,wind_speed_10m,wind_direction_10m,"
                    "precipitation,is_day"
                ),
                "timezone": "auto",
                "wind_speed_unit": "kmh",
                "temperature_unit": "celsius",
            },
            timeout=8,
        )
        wx_resp.raise_for_status()
        wx_data = wx_resp.json()
    except requests.RequestException as exc:
        return {"error": f"Weather request failed: {exc}"}
    except ValueError:
        return {"error": "Weather endpoint returned a non-JSON response."}

    cur = wx_data.get("current") or {}
    code = cur.get("weather_code")
    description = _WMO_DESCRIPTIONS.get(code, f"weather code {code}")

    return {
        "location": {
            "city": resolved_name,
            "admin_region": resolved_admin,
            "country": resolved_country,
            "latitude": lat,
            "longitude": lon,
            "timezone": wx_data.get("timezone"),
        },
        "observed_at": cur.get("time"),
        "is_day": bool(cur.get("is_day")),
        "description": description,
        "temperature_c": cur.get("temperature_2m"),
        "feels_like_c": cur.get("apparent_temperature"),
        "humidity_pct": cur.get("relative_humidity_2m"),
        "precipitation_mm": cur.get("precipitation"),
        "wind_speed_kmh": cur.get("wind_speed_10m"),
        "wind_direction_deg": cur.get("wind_direction_10m"),
        "source": "open-meteo.com",
    }


# ===========================================================================
# Tool registry — what Claude is told about + how we dispatch
# ===========================================================================
# Each entry has:
#   - the Anthropic-format declaration (name, description, input_schema)
#   - a Python callable that takes a dict of arguments and returns a dict
TOOLS_FOR_CLAUDE: list[dict] = [
    {
        "name": "get_current_time",
        "description": (
            "Get the current date and time in any timezone. Use this "
            "whenever the user asks about the current time, date, or day "
            "of week in a specific place. Accepts IANA timezone names "
            "like 'Asia/Tokyo' or common city/country names like 'Tokyo' "
            "or 'India' (which will be mapped to a canonical zone)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "timezone": {
                    "type": "string",
                    "description": (
                        "IANA timezone (e.g. 'Europe/London') or common "
                        "city/country name (e.g. 'Tokyo', 'India'). "
                        "Defaults to UTC if omitted."
                    ),
                }
            },
            "required": ["timezone"],
        },
    },
    {
        "name": "get_current_weather",
        "description": (
            "Get the current weather conditions for any city in the "
            "world. Returns temperature, humidity, wind, and a "
            "human-readable description. Use this whenever the user "
            "asks about the current weather, temperature, or conditions "
            "in a specific place."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "City name, e.g. 'Mumbai', 'New York'.",
                },
                "country": {
                    "type": "string",
                    "description": (
                        "Optional country name or ISO code to "
                        "disambiguate (e.g. 'United Kingdom' or 'GB'). "
                        "Use when the city name is ambiguous."
                    ),
                },
            },
            "required": ["city"],
        },
    },
]

TOOL_DISPATCH = {
    "get_current_time": get_current_time,
    "get_current_weather": get_current_weather,
}


def dispatch_tool(name: str, args: dict) -> tuple[dict, bool]:
    """
    Execute a tool by name and return (output_dict, is_error).

    On exception we still return a dict so the agent loop can hand it
    back to Claude as an is_error=true tool_result block, letting Claude
    self-correct.
    """
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"Unknown tool: {name!r}"}, True
    try:
        result = fn(**(args or {}))
    except TypeError as exc:
        return {"error": f"Bad arguments for {name}: {exc}"}, True
    except Exception as exc:  # noqa: BLE001
        log.exception("Tool %s raised", name)
        return {"error": f"{type(exc).__name__}: {exc}"}, True

    is_error = isinstance(result, dict) and "error" in result and len(result) == 1
    return result, is_error


# ===========================================================================
# The tool-use loop
# ===========================================================================
def chat_with_tools(user_message: str) -> tuple[str, list[str]]:
    """
    Send one user message through the full Anthropic tool-use loop.

    Returns:
      reply_text   -- the assistant's final natural-language answer.
      activity_log -- a list of human-readable lines describing every
                      tool_call / tool_result that happened, suitable
                      for the activity panel.
    """
    if not user_message or not user_message.strip():
        return "Please type a message.", []

    messages: list[dict] = [
        {"role": "user", "content": user_message},
    ]
    activity: list[str] = []
    final_text_parts: list[str] = []

    for iteration in range(MAX_TOOL_ITERATIONS):
        activity.append(f"_Iteration {iteration + 1}: calling Claude..._")
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                temperature=0.0,
                system=SYSTEM_PROMPT,
                tools=TOOLS_FOR_CLAUDE,
                messages=messages,
            )
        except APIError as exc:
            return f"❌ API error: {exc}", activity

        # Persist the assistant's response verbatim so any tool_use IDs
        # match the tool_result we send back next.
        messages.append({"role": "assistant", "content": response.content})

        # Walk the content blocks. There can be text + tool_use blocks
        # in the same response.
        tool_uses_this_round: list[dict] = []
        for block in response.content:
            if block.type == "text":
                if block.text.strip():
                    final_text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses_this_round.append(
                    {"id": block.id, "name": block.name, "input": block.input}
                )
                activity.append(
                    f"### 🛠️ Tool call: `{block.name}`\n"
                    f"```json\n{json.dumps(block.input, indent=2)}\n```"
                )

        # If Claude is done (no more tool_use blocks), we're done.
        if response.stop_reason != "tool_use":
            break

        # Otherwise, execute every requested tool and feed the results
        # back as a single user message with N tool_result blocks.
        tool_result_blocks: list[dict] = []
        for tu in tool_uses_this_round:
            output, is_error = dispatch_tool(tu["name"], tu["input"])
            icon = "❌" if is_error else "✅"
            preview = json.dumps(output, indent=2, default=str)
            if len(preview) > 600:
                preview = preview[:600] + "\n  ... (truncated)"
            activity.append(
                f"### {icon} Result from `{tu['name']}`\n"
                f"```json\n{preview}\n```"
            )
            tool_result_blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(output, default=str),
                    **({"is_error": True} if is_error else {}),
                }
            )

        messages.append({"role": "user", "content": tool_result_blocks})
    else:
        activity.append(
            f"_Stopped after {MAX_TOOL_ITERATIONS} iterations (safety cap)._"
        )

    reply = "".join(final_text_parts).strip() or "_(no text reply)_"
    return reply, activity


# ===========================================================================
# Gradio UI
# ===========================================================================
EXAMPLE_PROMPTS = [
    "What's the current time in Tokyo?",
    "What time is it in New York right now?",
    "What's the weather like in Mumbai?",
    "How's the weather in London today?",
    "Tell me the current time in Sydney and the weather in Singapore.",
    "What is 17 times 24?",  # should NOT call any tool
    "Explain what an IANA timezone is.",  # should NOT call any tool
]


def run_chat(user_message: str) -> tuple[str, str]:
    """Gradio callback: returns (reply_md, activity_md)."""
    reply, activity = chat_with_tools(user_message)
    activity_md = (
        "\n\n".join(activity) if activity
        else "_No tool calls were made for this question._"
    )
    return reply, activity_md


def build_ui() -> gr.Blocks:
    with gr.Blocks(
        title="Claude with Tools (Stage 0+)",
        theme=gr.themes.Soft(primary_hue="sky", neutral_hue="slate"),
    ) as demo:
        gr.Markdown(
            "# 🛠️ Claude with Tools (Stage 0+)\n"
            "Single-turn Stage 0, upgraded with **two real tools**:\n\n"
            "- ⏰ **get_current_time** — current date/time in any timezone, "
            "via [timeapi.io](https://timeapi.io) (with a local fallback).\n"
            "- 🌤️ **get_current_weather** — current weather for any city in "
            "the world, via [open-meteo.com](https://open-meteo.com) "
            "(geocoding + forecast endpoints; no API key needed).\n\n"
            "When you ask about the current time or weather, Claude will "
            "decide to call the right tool, we'll execute it locally, hand "
            "the result back, and Claude will summarize the answer for you. "
            "For unrelated questions Claude just answers directly without "
            "any tool calls.\n\n"
            f"_Model: `{MODEL}`_"
        )

        with gr.Row():
            with gr.Column(scale=3):
                user_input = gr.Textbox(
                    label="Your question",
                    placeholder=(
                        "Try: 'What time is it in Tokyo?' or "
                        "'What's the weather in Mumbai?'"
                    ),
                    lines=3,
                    autofocus=True,
                )
                with gr.Row():
                    run_btn = gr.Button("Ask", variant="primary")
                    clear_btn = gr.Button("Clear", size="sm")
                gr.Examples(examples=EXAMPLE_PROMPTS, inputs=user_input,
                            label="Example prompts (click to fill)")
            with gr.Column(scale=4):
                reply_out = gr.Markdown(
                    label="Reply",
                    value="_Claude's reply will appear here._",
                    height=200,
                )

        gr.Markdown("---\n## 🔍 Tool activity for the latest question")
        gr.Markdown(
            "_Every tool call Claude requested, and every result we fed "
            "back, in order. Empty if Claude answered without tools._"
        )
        activity_out = gr.Markdown(
            value="_No question asked yet._",
            height=380,
        )

        # ---- Wiring ----
        run_btn.click(fn=run_chat, inputs=user_input, outputs=[reply_out, activity_out])
        user_input.submit(fn=run_chat, inputs=user_input,
                          outputs=[reply_out, activity_out])
        clear_btn.click(
            fn=lambda: ("", "_Claude's reply will appear here._",
                        "_No question asked yet._"),
            outputs=[user_input, reply_out, activity_out],
        )

        gr.Markdown(
            "---\n_Stage 0+ adds tool use only. Memory and multi-turn chat "
            "come in later stages of the training._"
        )

    return demo


if __name__ == "__main__":
    build_ui().launch(server_name="127.0.0.1", server_port=7860, share=False)
