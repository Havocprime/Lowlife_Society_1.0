from __future__ import annotations
import discord
from src.db import dal

def character_embed(player_row, character_row) -> discord.Embed:
    e = discord.Embed(title="LOWLIFE — Character Sheet", color=discord.Color.gold())
    e.set_author(name=player_row["username"])
    e.add_field(name="Player", value=f"Discord ID: `{player_row['discord_id']}`", inline=False)
    if character_row:
        e.add_field(name="Character", value=f"**{character_row['codename']}**  |  Faction: {character_row['faction'] or '-'}", inline=False)
        # pull profile
        prof = _get_profile(character_row["id"])
        e.add_field(name="Vitals", value=f"HP **{prof['hp']}**  •  Stamina **{prof['stamina']}**  •  Notoriety **{prof['notoriety']}**", inline=False)
        # wallet
        bal = dal.get_balance("character", character_row["id"])
        e.add_field(name="Wallet", value=f"Pitch Coins: **{bal}**", inline=False)
    else:
        e.add_field(name="Character", value="No character yet. Use `/onboard`.", inline=False)
    return e

def _get_profile(character_id: int):
    # Profiles row guaranteed by DAL create_character
    import sqlite3
    from src.core.settings import SETTINGS
    con = sqlite3.connect(SETTINGS.db_path); con.row_factory = sqlite3.Row
    return con.execute("SELECT * FROM profiles WHERE character_id=?", (character_id,)).fetchone()
