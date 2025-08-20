# =============================




async def main():
load_dotenv(ENV_PATH) # loads .env if present


token = os.getenv("DISCORD_TOKEN")
if not token:
raise SystemExit("DISCORD_TOKEN missing in .env")


guild_id = os.getenv("DISCORD_GUILD_ID")
intents = build_intents()


bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree


@bot.event
async def on_ready():
log.info("logging in using static token")
log.info("Logged in as %s (%s)", bot.user, bot.user and bot.user.id)


# Load rules/templates early
try:
load_rules()
except Exception as e: # pragma: no cover
log.warning("rules load error: %s", e)


# Register command groups
register_players(tree)
register_inventory_commands(tree)
register_duel(tree)
register_updates(tree)


# Guild-only sync (faster while developing)
if guild_id:
synced = await tree.sync(guild=discord.Object(id=int(guild_id)))
log.info("Synced commands to guild %s -> %s", guild_id, [c.name for c in synced])
else:
synced = await tree.sync()
log.info("Synced global commands -> %s", [c.name for c in synced])


await bot.start(token)




if __name__ == "__main__":
try:
asyncio.run(main())
except KeyboardInterrupt:
pass

