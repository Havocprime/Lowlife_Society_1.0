# Lowlife Intake Module (Join Snapshot + Mugshot + Admin Inspector)

## Files
- src/core/schema.sql
- src/core/db.py
- src/core/portraits.py
- src/core/risk.py
- src/cogs/invite_tracker.py
- src/cogs/member_intake.py
- src/cogs/admin_inspector.py
- scripts/init_db.py

## Quick Setup
1) Copy these files into your repo, preserving paths.
2) From repo root: `python -m scripts.init_db` (creates `data/lowlife.db`).
3) Set `.env`:
   - `DISCORD_TOKEN=...`
   - `WELCOME_CHANNEL_ID=...` (text channel ID for mugshots)
   - `ADMIN_ROLE_ID=...` (optional; admins always allowed)
4) Ensure intents enabled in Dev Portal (Server Members; Presence optional). In code, pass `intents=discord.Intents.all()` or at minimum `Intents.members=True`.
5) Load extensions at startup:
   ```py
   await bot.load_extension("src.cogs.invite_tracker")
   await bot.load_extension("src.cogs.member_intake")
   await bot.load_extension("src.cogs.admin_inspector")
   ```
6) Give bot `View Invites` permission to attribute referrals.
7) Test `/inspect` and simulate a join to see the mugshot.