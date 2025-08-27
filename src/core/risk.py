from datetime import datetime, timezone


def compute_risk(snapshot: dict) -> tuple[int, list[str]]:
    reasons = []
    score = 0
    user = snapshot.get("user", {})
    member = snapshot.get("member", {})
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
    if not user.get("banner_url"):
        score += 3
        reasons.append("no_banner")
    if not user.get("avatar_url"):
        score += 15
        reasons.append("default_avatar")
    roles = member.get("roles", [])
    if len(roles) <= 1:
        score += 10
        reasons.append("no_roles")
    if member.get("pending"):
        score += 10
        reasons.append("membership_screen_pending")
    return score, reasons
