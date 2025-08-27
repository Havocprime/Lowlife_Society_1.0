from datetime import datetime, timezone


def compute_risk(snapshot: dict) -> tuple[int, list[str]]:
    reasons: list[str] = []
    score = 0

    user = snapshot.get("user", {})
    member = snapshot.get("member", {})

    # Very new account (< 7 days)
    created = user.get("created_at")
    if created:
        try:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created_dt).days
            if age_days < 7:
                score += 30
                reasons.append("very_new_account")
        except Exception:
            pass

    # Default avatar (no custom) — Discord always has a display avatar, so this is more of a heuristic.
    if not user.get("avatar_url"):
        score += 15
        reasons.append("default_avatar")

    # No roles beyond @everyone
    roles = member.get("roles", [])
    if len(roles) <= 1:
        score += 10
        reasons.append("no_roles")

    # Pending screen
    if member.get("pending"):
        score += 10
        reasons.append("membership_screen_pending")

    # No banner
    if not user.get("banner_url"):
        score += 3
        reasons.append("no_banner")

    return score, reasons
