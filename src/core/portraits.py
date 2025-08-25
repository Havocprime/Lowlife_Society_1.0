from pathlib import Path
PORTRAIT_DIR = Path("game/assets/portraits")
def list_portraits():
    if not PORTRAIT_DIR.exists():
        return []
    exts = {".png",".jpg",".jpeg",".webp"}
    return sorted([p for p in PORTRAIT_DIR.iterdir() if p.suffix.lower() in exts])
def pick_portrait_for_user(user_id: int) -> str | None:
    files = list_portraits()
    if not files:
        return None
    return str(files[user_id % len(files)])