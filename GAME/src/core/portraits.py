from pathlib import Path

# Directory containing portrait images (png/jpg/webp). Update if different.
PORTRAIT_DIR = Path("game/assets/portraits")

def list_portraits():
    if not PORTRAIT_DIR.exists():
        return []
    return sorted([p for p in PORTRAIT_DIR.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])

def pick_portrait_for_user(user_id: int) -> str | None:
    files = list_portraits()
    if not files:
        return None
    idx = user_id % len(files)
    return str(files[idx])