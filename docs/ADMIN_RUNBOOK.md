
## B) `docs/ADMIN_RUNBOOK.md`
```markdown
# LOWLIFE — Admin Runbook

## Day-to-day

### Sync commands
- `/sync` — default sync to guild
- `/sync global` — push to global
- `/sync copy` — copy global → guild

> If you ever see “Unknown interaction”, it usually means another handler acknowledged first. We guard against dupes, but keep a single `/sync` command in the repo.

### Health
- `/health` — returns:
  - DB RW check ✅/❌ (temp table insert/rollback)
  - Event count (last 1h)
  - Latency (ms)
  - APP_ENV and DB path

### Audit
- `/audit_recent [limit]` — last N events (default 20)
- `/audit_user @member [limit]` — events for a user

Behind the scenes, `core/audit.py` writes a lightweight audit row per command to `GAME/data/audit.sqlite`. It never blocks the interaction token and logs after the handler.

### Economy / Items
- `/character` — shows wallet + top 5 inventory
- `character_give_test_item` (ADMIN) — mint a test item with optional coin bonus; idempotent transactions supported via DAL.

### Export / Backup
- `scripts/export_players.py` → `GAME/var/exports/players-*.csv`
- `scripts/export_events.py`  → `GAME/var/exports/events-*.csv`
- `backup_db.bat` — ad-hoc DB backup (zip optional)

Run from repo root:
```powershell
$env:PYTHONPATH="$PWD"
python .\scripts\export_players.py
python .\scripts\export_events.py
