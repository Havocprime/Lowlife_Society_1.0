# src/bot/commands/players.py
from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

import discord
from discord import app_commands
from pydantic import BaseModel

# Tiny JSON "DB" for the prototype
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "players.json"


def _load_db() -> Dict[str, Any]:
    if DB_PATH.exists():
        try:
            return json.loads(DB_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def _save_db(db: Dict[str, Any]) -> None:
    DB_PATH.write_text(json.dumps(db, indent=2), encoding="utf-8")


class Player(BaseModel):
    user_id: str
    alias: str
    birth_district: str = "Rustwater"
    native_skill: str = "Lockpicking"
    baseline: str = "Fit"

    # HUD-facing fields
    cash: int = 0
    net_worth: int = 0
    level: int = 1
    equipped: str = "Fists"
    weight: float = 0.0
    capacity: float = 30.0
    blood: int = 0  # placeholder for bleeding/blood metric


def register(tree: app_commands.CommandTree, templates: Optional[Dict[str, Any]] = None) -> None:
    """
    Register /create and /sheet onto the provided CommandTree.

    'templates' is optional so this function works whether bot.py calls
    register(tree) or register(tree, templates).
    """
    default_sheet_tpl = {
        "title": "🧬 {alias} — Birth Packet",
        "fields": [
            {"name": "Birth District", "value": "{district}", "inline": True},
            {"name": "Native Skill",   "value": "{skill}",    "inline": True},
            {"name": "Baseline",       "value": "{baseline}", "inline": True},
        ],
    }
    sheet_tpl = (templates or {}).get("character_sheet", default_sheet_tpl)

    @app_commands.command(name="create", description="Create your Lowlife character.")
    @app_commands.describe(alias="Your street name (displayed publicly)")
    async def create(inter: discord.Interaction, alias: str):
        db = _load_db()
        pid = str(inter.user.id)
        if pid in db:
            await inter.response.send_message(
                "You already have a character. Use **/sheet** to view it.",
                ephemeral=True,
            )
            return
        player = Player(user_id=pid, alias=alias)
        db[pid] = player.model_dump()
        _save_db(db)
        await inter.response.send_message(
            f"Created **{alias}**. Use **/sheet** to view your birth packet.",
            ephemeral=True,
        )

    @app_commands.command(name="sheet", description="Show a character’s sheet (yours by default).")
    @app_commands.describe(member="Whose sheet to view (optional)")
    async def sheet(inter: discord.Interaction, member: Optional[discord.Member] = None):
        db = _load_db()
        target = member or inter.user
        pid = str(target.id)
        if pid not in db:
            await inter.response.send_message(
                "No character found. Use **/create** first." if target == inter.user
                else f"{target.mention} has no character.",
                ephemeral=True,
            )
            return

        p = db[pid]
        embed = discord.Embed(title=sheet_tpl["title"].format(alias=p.get("alias", "Unknown")))

        mapping = {
            "district": p.get("birth_district", "Rustwater"),
            "skill":    p.get("native_skill",    "Lockpicking"),
            "baseline": p.get("baseline",        "Fit"),
        }
        for f in sheet_tpl.get("fields", []):
            embed.add_field(
                name=f.get("name", "Field"),
                value=f.get("value", "").format(**mapping),
                inline=bool(f.get("inline", False)),
            )
        await inter.response.send_message(embed=embed)

    # Attach to tree explicitly (avoid double decorators elsewhere)
    tree.add_command(create)
    tree.add_command(sheet)
    print("Registered player commands: /create, /sheet")
