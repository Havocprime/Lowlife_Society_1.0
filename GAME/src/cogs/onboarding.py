# GAME/src/cogs/onboarding.py
from __future__ import annotations

import discord
from discord.ext import commands

# ──────────────────────────────────────────────────────────────────────────────
# PLACE YOUR REAL ONBOARDING COG HERE (if you have one)
#   Expected class name: Onboarding   (preferred)
#   Acceptable aliases: OnboardingCog, Onboard, OnboardingFlow
#
# Example:
# class Onboarding(commands.Cog):
#     ...
# ──────────────────────────────────────────────────────────────────────────────


# ──────────────────────────────────────────────────────────────────────────────
# Fallback (minimal) onboarding cog
#   This only exists so the bot keeps loading if your real class is missing.
#   Safe to leave in the file; it will be ignored when a real class is present.
# ──────────────────────────────────────────────────────────────────────────────
class _FallbackOnboarding(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="onboard", description="Begin the onboarding flow.")
    async def onboard(self, ctx: commands.Context) -> None:
        await ctx.reply(
            "🧭 Onboarding is temporarily using a fallback handler. "
            "If you expected the full multi-step flow, make sure the `Onboarding` "
            "cog class is defined in this file (see the comment block near the top).",
            ephemeral=True if hasattr(ctx, "reply") else False,  # works for both slash & text
        )


# ──────────────────────────────────────────────────────────────────────────────
# Robust, idempotent setup
#   - Finds your onboarding cog class by name (supports a few aliases).
#   - Avoids duplicate-cog errors on hot reloads.
#   - Never touches unrelated cogs (e.g., ItemMagazine).
# ──────────────────────────────────────────────────────────────────────────────
def _resolve_onboarding_cls():
    """Find the real onboarding cog class if present; else return the fallback."""
    for name in ("Onboarding", "OnboardingCog", "Onboard", "OnboardingFlow"):
        cls = globals().get(name)
        if isinstance(cls, type) and issubclass(cls, commands.Cog):
            return cls
    return _FallbackOnboarding


async def setup(bot: commands.Bot):
    CogClass = _resolve_onboarding_cls()
    # Don’t double-add the cog if this module is reloaded.
    if bot.get_cog(CogClass.__name__) is None:
        await bot.add_cog(CogClass(bot))
