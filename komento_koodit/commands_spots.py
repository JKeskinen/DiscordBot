import os
import json
import time
import asyncio
import logging
from typing import Any, Dict, List, Tuple

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

try:
    from . import check_capacity as capacity_mod
except Exception:  # pragma: no cover
    capacity_mod = None  # type: ignore[assignment]


logger = logging.getLogger(__name__)


async def _send_spots_lines(channel: Any, lines: List[str]) -> None:
    max_len = 1900
    cur: List[str] = []
    cur_len = 0
    for ln in lines:
        if cur and cur_len + len(ln) + 1 > max_len:
            try:
                Embed_cls = getattr(discord, "Embed", None)
                if Embed_cls:
                    embed = Embed_cls(title="Kilpailut, joissa vähän paikkoja:", description="\n".join(cur))
                    await channel.send(embed=embed)
                else:
                    await channel.send("\n".join(cur))
            except Exception:
                await channel.send("\n".join(cur))
            cur = []
            cur_len = 0
        cur.append(ln)
        cur_len += len(ln) + 1

    if cur:
        try:
            Embed_cls = getattr(discord, "Embed", None)
            if Embed_cls:
                embed = Embed_cls(title="Kilpailut, joissa vähän paikkoja:", description="\n".join(cur))
                await channel.send(embed=embed)
            else:
                await channel.send("\n".join(cur))
        except Exception:
            await channel.send("\n".join(cur))


async def handle_spots(message: Any, parts: Any) -> None:
    """Handle the !spots command (capacity alerts)."""
    channel = message.channel
    arg_text = " ".join(parts[1:]).strip() if len(parts) > 1 else ""
    provided_res: Any | None = None

    # Special keyword to force reading CAPACITY_ALERTS.json
    if arg_text and arg_text.lower() in (
        "alerts",
        "capacity_alerts.json",
        "capacity_alerts",
        "capalerts",
        "file",
    ):
        try:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            alert_path = os.path.join(base_dir, "CAPACITY_ALERTS.json")
            if os.path.exists(alert_path):
                with open(alert_path, "r", encoding="utf-8") as f:
                    provided_res = json.load(f)
        except Exception:
            provided_res = None

    # If no inline/attachment JSON was provided, prefer a recent cached
    # CAPACITY_ALERTS.json in the project root to avoid running a slow
    # live scan when the user simply typed `!spots`.
    try:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        alert_path = os.path.join(base_dir, "CAPACITY_ALERTS.json")
        if provided_res is None and not arg_text and os.path.exists(alert_path):
            age = time.time() - os.path.getmtime(alert_path)
            # prefer cache younger than 1 hour (3600s)
            if age < 3600:
                try:
                    with open(alert_path, "r", encoding="utf-8") as f:
                        provided_res = json.load(f)
                except Exception:
                    provided_res = None
    except Exception:
        provided_res = None

    # If a JSON payload was provided, use it directly and skip background scan
    if provided_res is not None:
        res = (
            provided_res
            if isinstance(provided_res, list)
            else (provided_res.get("alerts") if isinstance(provided_res, dict) and provided_res.get("alerts") else [])
        )
        if not res:
            await channel.send("Ei paikkoja ilmoituksissa (JSON tyhjä).")
            return

        # Build lines and send immediately (no background task)
        lines: List[str] = []
        for c in res[:200]:
            name = c.get("title") or c.get("name") or c.get("name_en") or c.get("event") or ""
            url = c.get("url") or ""
            reg = c.get("registered")
            lim = c.get("limit")
            rem = c.get("remaining")
            # prefer computing remaining from reg/lim when possible
            if reg is not None and lim is not None:
                disp = f"{reg}/{lim}"
            elif reg is not None and lim is None:
                disp = f"{reg}/?"
            elif reg is None and lim is not None:
                disp = f"?/{lim}"
            else:
                disp = f'jäljellä {rem if rem is not None else "?"} paikkaa'

            if url:
                lines.append(f"• [{name}]({url}) — {disp}")
            else:
                lines.append(f"• {name} — {disp}")

        await _send_spots_lines(channel, lines)
        return

    # Otherwise perform the background capacity check as before
    await channel.send("Tarkistan paikkojen tilannetta (suoritetaan taustalla)...")

    loop = asyncio.get_running_loop()

    def run_check() -> Any:
        try:
            if capacity_mod is None or not hasattr(capacity_mod, "find_low_capacity"):
                logger.warning("Capacity module not available; skipping live check")
                return []
            return capacity_mod.find_low_capacity()
        except Exception as e:  # pragma: no cover - defensive
            logger.exception("Error in capacity check: %s", e)
            return e

    future = loop.run_in_executor(None, run_check)

    async def handle_result(fut: Any) -> None:
        res = await fut
        if isinstance(res, Exception):
            await channel.send(f"Virhe paikkojen tarkistuksessa: {res}")
            return
        if not res:
            await channel.send("Ei kilpailuja, joissa vähän paikkoja.")
            return

        # Build lines and chunk into Discord-safe messages (<= ~2000 chars)
        lines: List[str] = []
        for c in res[:200]:
            name = c.get("title") or c.get("name") or c.get("name_en") or c.get("event") or ""
            url = c.get("url") or ""
            reg = c.get("registered")
            lim = c.get("limit")
            rem = c.get("remaining")
            if reg is not None and lim is not None:
                disp = f"{reg}/{lim}"
            elif reg is not None and lim is None:
                disp = f"{reg}/?"
            elif reg is None and lim is not None:
                disp = f"?/{lim}"
            else:
                disp = f'jäljellä {rem if rem is not None else "?"} paikkaa'
            lines.append(f"• {name} — {disp} — {url}")

        await _send_spots_lines(channel, lines)

    asyncio.create_task(handle_result(future))
