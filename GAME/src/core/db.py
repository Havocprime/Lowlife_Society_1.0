import json, sqlite3
from pathlib import Path

DB_PATH = Path("data/lowlife.db")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init():
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with conn() as db:
        db.executescript(schema)

def upsert_player(snapshot: dict):
    user = snapshot.get("user", {})
    member = snapshot.get("member", {})
    derived = snapshot.get("derived", {})
    ctx = snapshot.get("join_context", {})

    roles = member.get("roles", [])
    top_role = roles[-1] if roles else {"id": None, "name": None}

    with conn() as db:
        db.execute("""
        INSERT INTO players (discord_id,name,global_name,nickname,is_bot,is_system,created_at_utc,joined_at_utc,
            avatar_url,banner_url,accent_color,premium_since_utc,top_role_id,top_role_name,status,public_flags,
            communication_disabled_until_utc,veteran_rank,portrait_asset,invite_code,inviter_id,invite_channel_id,
            risk_score,risk_reasons,first_snapshot_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(discord_id) DO UPDATE SET
          name=excluded.name, global_name=excluded.global_name, nickname=excluded.nickname,
          joined_at_utc=excluded.joined_at_utc, avatar_url=excluded.avatar_url, banner_url=excluded.banner_url,
          accent_color=excluded.accent_color, premium_since_utc=excluded.premium_since_utc,
          top_role_id=excluded.top_role_id, top_role_name=excluded.top_role_name, status=excluded.status,
          communication_disabled_until_utc=excluded.communication_disabled_until_utc,
          veteran_rank=excluded.veteran_rank, portrait_asset=excluded.portrait_asset,
          invite_code=excluded.invite_code, inviter_id=excluded.inviter_id, invite_channel_id=excluded.invite_channel_id,
          risk_score=excluded.risk_score, risk_reasons=excluded.risk_reasons, first_snapshot_json=excluded.first_snapshot_json
        """, (
            user.get("id"), user.get("name"), user.get("global_name"), member.get("nick"),
            bool(user.get("bot")), bool(user.get("system")),
            user.get("created_at"), member.get("joined_at"), user.get("avatar_url"), user.get("banner_url"),
            user.get("accent_color"), member.get("premium_since"), top_role.get("id"), top_role.get("name"),
            member.get("status"), user.get("public_flags"), member.get("communication_disabled_until"),
            derived.get("veteran_rank"), derived.get("portrait_asset"), ctx.get("invite_code"),
            ctx.get("inviter_id"), ctx.get("invite_channel_id"),
            int(derived.get("risk_score", 0)), json.dumps(derived.get("risk_reasons", [])),
            json.dumps(snapshot)
        ))

        db.execute("DELETE FROM player_roles WHERE discord_id=?", (user.get("id"),))
        for r in roles:
            db.execute("INSERT OR IGNORE INTO player_roles (discord_id,role_id,role_name) VALUES (?,?,?)",
                       (user.get("id"), r.get("id"), r.get("name")))