# Lowlife 1.0 — MVP One‑Pager
Date: 2025-08-14

## Goal
Ship a Discord-first MUD RPG where the core loop (create → fight → loot → heal → progress) works with **distance-based PvP** and an **offline AI defender**.

## Player Journey (Vertical Slice)
1) Create character → receive Birth Packet & starting gear.
2) Explore slice district → take a mission → encounter enemies.
3) Engage in combat (live PvP or AI defender when opponent is offline) with range gates.
4) Win/lose → loot/injury/insurance logic.
5) Heal, level up, equip upgrades → repeat.

## Systems in MVP
- Character creation (Birth Packet)
- Inventory & equipment (weight, concealment, durability)
- Combat (distance, movement, accuracy/damage, status effects, grapple, suppression)
- AI defender v1 (range-aware)
- Leveling/progression (XP, stat points, daily profession ticks)
- Missions/jobs v1 (3 basic jobs, 6–10 missions)
- Shops/loot economy primitives
- Security hooks (verification, cooldowns, logs)
- Embed Manager v1 (sheets, logs, shops, missions)
- Observability (structured logs, metrics), backups

## Non-Goals (defer)
- Cosmetics marketplace, advanced crafting trees, additional districts beyond first 3
- Rune traders & ultra-rare events, clubs/fame/rep meta

## Definition of Done (DoD)
- ✅ Distance-based combat flow implemented (Close/Near/Mid/Far/OoR).
- ✅ Live PvP + offline AI defender playable and logged in embeds.
- ✅ Inventory/equipment functional with weight & concealment; loot/insurance rules.
- ✅ XP curve balanced for slice; mission chains complete.
- ✅ Security protections enforced; admin/audit tools available.
- ✅ Observability, backups, failover verified on staging.
- ✅ FTUE tutorial and consistent embed styles.
