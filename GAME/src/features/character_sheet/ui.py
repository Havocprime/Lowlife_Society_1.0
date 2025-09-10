from __future__ import annotations

import discord

from src.db import dal


def character_embed(player_row, character_row) -> discord.Embed:
    e = discord.Embed(title="LOWLIFE â€” Character Sheet", color=discord.Color.gold())
    e.set_author(name=player_row["username"])
    e.add_field(name="Player", value=f"Discord ID: `{player_row['discord_id']}`", inline=False)

    if character_row:
        e.add_field(
            name="Character",
            value=f"**{character_row['codename']}**  â€¢  Faction: {character_row['faction'] or '-'}",
            inline=False,
        )
        # vitals
        prof = _get_profile(character_row["id"])
        e.add_field(
            name="Vitals",
            value=f"HP **{prof['hp']}**  â€¢  Stamina **{prof['stamina']}**  â€¢  Notoriety **{prof['notoriety']}**",
            inline=False,
        )
        # wallet
        bal = dal.get_balance("character", character_row["id"])
        e.add_field(name="Wallet", value=f"Pitch Coins: **{bal}**", inline=True)

        # inventory preview
        inv = dal.list_inventory(character_row["id"])[:5]
        if inv:
            lines = [
                f"â€¢ **{r['name']}** x{r['qty']} _(R:{r['rarity'] or '-'}, {r['class'] or '-'})_"
                for r in inv
            ]
            e.add_field(name="Inventory (Top 5)", value="\n".join(lines), inline=False)
        else:
            e.add_field(name="Inventory", value="_empty_", inline=False)
    else:
        e.add_field(name="Character", value="No character yet. Use `/onboard`.", inline=False)
    return e
