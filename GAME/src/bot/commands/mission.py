import discord
from discord.ext import commands

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def mission(ctx):
    embed = discord.Embed(
        title="📖 GDD / Mission 1.0",
        description=(
            "**Lowlife Society** is officially entering its first structured phase of development.\n\n"
            "This is our **Game Design Document (GDD)** and roadmap checkpoint: *Mission 1.0.*\n\n"
            "We’ve now indexed **91 distinct tangents** across 7 categories:\n"
            "- 🟥 Core (5)\n"
            "- 🟧 Gameplay (15)\n"
            "- 🟨 Economy & Rewards (12)\n"
            "- 🟩 World & Environment (20)\n"
            "- 🟦 Social & Interaction (12)\n"
            "- 🟪 Infrastructure (19)\n"
            "- ⚫ Other / Branding (8)\n\n"
            "**Overall Progress:** ~15% built\n"
            "➡️ Strongest pillar: *Economy & Reward Systems*\n"
            "➡️ Weakest pillar: *World & Branding* (still conceptual)\n\n"
            "This is our **Mission 1.0:** establish the CORE framework, solidify Combat + Rewardius, "
            "and prepare the City Hub foundation.\n\n"
            "Every action from here plugs into the Custodian log. Nothing is lost. Nothing is wasted. This is the climb."
        ),
        color=discord.Color.red(),
    )
    await ctx.send(embed=embed)


bot.run("")
