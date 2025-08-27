from __future__ import annotations

import discord

from src.core.duel_core import GrappleState, RangeBand


def _range_label(r: RangeBand) -> str:
    return {r.CLOSE: "CLOSE", r.NEAR: "NEAR", r.MID: "MID", r.FAR: "FAR", r.OOR: "OUT"}[r]


def build_combat_embed(session: dict) -> discord.Embed:
    a, b = session["a"], session["b"]
    r = session["range"]
    g = session["grapple"]
    hp = session.get("hp", {})
    log_lines = session.get("log", [])[-6:]

    e = discord.Embed(title="LOWLIFE — Duel", color=0x00FFB7)
    e.add_field(name="Range", value=_range_label(r), inline=True)
    e.add_field(name="Grapple", value=GrappleState(g).name, inline=True)
    e.add_field(name="Players", value=f"<@{a}> vs <@{b}>", inline=False)

    if hp:
        ha = hp.get(a, "?")
        hb = hp.get(b, "?")
        e.add_field(name="HP", value=f"<@{a}>: **{ha}**\n<@{b}>: **{hb}**", inline=False)

    if log_lines:
        e.add_field(name="Log", value="\n".join(f"• {x}" for x in log_lines), inline=False)
    return e


def build_sheet_embed(p: dict, user_id: int) -> discord.Embed:
    e = discord.Embed(title=f"Sheet — <@{user_id}>", color=0x00B2FF)
    e.add_field(name="Class", value=p.get("cls", "wanderer"), inline=True)
    e.add_field(name="Level", value=str(p.get("lvl", 1)), inline=True)
    e.add_field(name="HP", value=str(p.get("hp", 10)), inline=True)
    e.add_field(name="Equipped", value=p.get("equipped", "fists"), inline=True)
    inv = p.get("inv", [])
    if inv:
        e.add_field(name="Inventory", value=", ".join(inv), inline=False)
    return e
