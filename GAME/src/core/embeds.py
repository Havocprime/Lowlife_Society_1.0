from __future__ import annotations
import os
import discord

ASSET_FOOTER = os.getenv("ASSET_FOOTER", "GAME/assets/embeds/footer.png")
ASSET_SEAL = os.getenv("ASSET_SEAL", "GAME/assets/embeds/lowlife_seal.png")

def build_combat_embed(state: dict) -> discord.Embed:
    e = discord.Embed(title="LOWLIFE — Duel", description="\n".join(state.get("log", [])))
    e.add_field(name="Range", value=str(state.get("range")))
    e.add_field(name="Grapple", value=str(state.get("grapple")))
    e.set_footer(text="Lowlife Society")
    return e

def build_update_embed(notes: str) -> discord.Embed:
    e = discord.Embed(title="LOWLIFE — Update", description=notes or "(no notes)")
    e.set_footer(text="Updatelog • Lowlife Certified")
    return e
