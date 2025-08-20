# Lowlife Society Changelog

---

## v0.1 – Initial Boot
**Date:** 2025-08-15  
**Summary:** First playable prototype of Lowlife Society duel system online.

### Added
- Core duel system (`duel.py`).
- Basic combat actions, turn order, and embeds.
- Player registration commands (`/create`, `/sheet`).
- Inventory commands integrated (equip, unequip, giveitem, genitem, transfer, mystats).

### Notes
- First stable version synced to guild.
- Known issues with AI finishers and action flow.

---

## v0.2 – Duel System Split & Battlefield Enhancements
**Date:** 2025-08-18  
**Summary:** Major refactor to split duel system into modules and add battlefield visual clarity.

### Added
- Modularized duel logic into:
  - `duel_core.py` → handles state & rules.
  - `duel_actions.py` → defines moves.
  - `duel_ai.py` → AI opponent logic.
  - `duel_render.py` → map + embed rendering.
  - `duel_commands.py` → slash commands (`/duel`, `/ai`).
- Battlefield visual upgrade:
  - Cover tiles (`🚧`, barrels).
  - Background tiles (`◽` daytime, ⬛ nighttime).
  - Hidden icons when in cover (shown in top row).
  - Placeholder `"..."` used instead of black tiles.

### Fixed
- AI “Not your turn” bug traced to `_maybe_offer_finisher` missing.
- Segmented imports to remove duplicate command registrations.

### Notes
- Old `duel.py` can be safely deleted after migration.
- Movement trail system under design.
