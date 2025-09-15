# save as tools/repair_repo_mojibake.py and run:  python tools/repair_repo_mojibake.py
import os, pathlib, io

ROOT = pathlib.Path(__file__).resolve().parents[1]  # repo root
EXTS = {".py", ".md", ".txt", ".json", ".ini", ".cfg", ".yaml", ".yml"}

def demojibake(s: str) -> str:
    # Only attempt if telltale bytes exist
    if "â" not in s and "Ã" not in s:
        return s
    try:
        return s.encode("latin1").decode("utf-8")
    except Exception:
        return s

def needs_fix(s: str) -> bool:
    return any(t in s for t in ("â€”","â€“","â€˜","â€™","â€œ","â€�","â€¦","â³","âŒ","â ","Ã—","Ã©"))

n = 0
for p in ROOT.rglob("*"):
    if p.suffix.lower() in EXTS and p.is_file():
        try:
            raw = p.read_text(encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            # try latin1 (file itself was saved mojibaked)
            raw = p.read_text(encoding="latin1", errors="strict")
        fixed = demojibake(raw)
        if fixed != raw or needs_fix(raw):
            bak = p.with_suffix(p.suffix + ".bak")
            if not bak.exists():
                bak.write_text(raw, encoding="utf-8", errors="ignore")
            p.write_text(fixed, encoding="utf-8")
            n += 1
print(f"Patched ~{n} files.")
