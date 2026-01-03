from typing import Any, List

try:
    import discord  # type: ignore[import]
except Exception:  # pragma: no cover
    discord = None  # type: ignore[assignment]

try:
    from . import help_texts as help_mod
except Exception:  # pragma: no cover
    help_mod = None  # type: ignore[assignment]


async def handle_help(message: Any, parts: Any) -> None:
    """Käsittele !ohje-komento (sekä mahdolliset aiheet)."""
    topic = ""
    if len(parts) > 1:
        topic = (parts[1] or "").strip().lower()

    if help_mod is not None and hasattr(help_mod, "get_help_message"):
        try:
            help_data = help_mod.get_help_message(topic)
            # help_texts.get_help_message returns a dict
            # with keys "title" and "description".
            title = str(help_data.get("title", "Ohje"))
            desc = str(help_data.get("description", ""))
            Embed_cls = getattr(discord, "Embed", None)
            if Embed_cls:
                # Use an accent colour so help looks like a
                # proper embed card instead of plain text.
                colour_kw = {}
                try:
                    Colour_cls = getattr(discord, "Colour", None)
                    if Colour_cls is not None and hasattr(Colour_cls, "orange"):
                        colour_kw["colour"] = Colour_cls.orange()
                except Exception:
                    colour_kw = {}
                embed = Embed_cls(title=title, description=desc, **colour_kw)
                await message.channel.send(embed=embed)
            else:
                await message.channel.send(f"{title}\n{desc}")
        except Exception:
            try:
                await message.channel.send("Virhe ohjetekstin näyttämisessä.")
            except Exception:
                pass
    else:
        try:
            await message.channel.send("Ohje ei ole käytettävissä.")
        except Exception:
            pass
