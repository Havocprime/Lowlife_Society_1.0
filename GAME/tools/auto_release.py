# FILE: tools/auto_release.py
from __future__ import annotations
import os, json, re, subprocess as sp, textwrap
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DATA.mkdir(parents=True, exist_ok=True)

VERSION_FILE = DATA / "version.txt"       # watched by your bot
NOTES_FILE   = DATA / "notes.md"          # watched by your bot
QUEUE_FILE   = DATA / "notes_queue.md"    # running list of pending lines
STATE_FILE   = DATA / "updates_state.json"  # {last_seen, queue_count}

THRESHOLD = int(os.getenv("LOWLIFE_CHANGE_THRESHOLD", "10"))

# ---------- git helpers
def sh(*args: str) -> str:
    return sp.check_output(args, cwd=str(ROOT), stderr=sp.DEVNULL).decode("utf-8", "ignore").strip()

def head() -> str:
    return sh("git", "rev-parse", "HEAD")

def subjects_between(a: str, b: str) -> list[str]:
    if a == b:
        return []
    out = sh("git", "log", "--pretty=%s", f"{a}..{b}")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]

# ---------- version helpers
_SEMVER = re.compile(r"^\s*(\d+)\.(\d+)(?:\.(\d+))?.*$")

def read_version() -> str:
    if VERSION_FILE.exists():
        v = VERSION_FILE.read_text(encoding="utf-8").strip()
        return v or "0.1"
    return "0.1"

def bump_minor(v: str) -> str:
    m = _SEMVER.match(v)
    if not m:
        return "0.1"  # fallback
    major, minor = int(m.group(1)), int(m.group(2))
    return f"{major}.{minor+1}"

# ---------- notes grouping (Conventional Commit friendly)
SECTIONS = [
    ("✨ Features", re.compile(r"^(feat|feature)(\(|:)", re.I)),
    ("🐞 Fixes",    re.compile(r"^(fix|bug)(\(|:)", re.I)),
    ("⚖️ Balance",  re.compile(r"^(balance|tweak)(\(|:)", re.I)),
    ("🧹 Refactor", re.compile(r"^(refactor)(\(|:)", re.I)),
    ("📝 Docs",     re.compile(r"^(docs)(\(|:)", re.I)),
    ("📦 Other",    re.compile(r".", re.I)),
]

def tidy(msg: str) -> str:
    # strip "type(scope): " prefix
    msg = re.sub(r"^[a-zA-Z]+(\([^)]+\))?:\s*", "", msg).strip()
    return (msg[:140] + "…") if len(msg) > 140 else msg

def compose_body(lines: list[str]) -> str:
    buckets = [(title, []) for title,_ in SECTIONS]
    for raw in lines:
        clean = tidy(raw.lstrip("• ").strip())
        for i, (title, rx) in enumerate(SECTIONS):
            if rx.search(raw):
                buckets[i][1].append(f"• {clean}")
                break
    parts = []
    for title, items in buckets:
        if items:
            parts.append(f"**{title}**")
            parts.extend(items[:12])
    text = "\n".join(parts) or "• misc improvements & fixes"
    return textwrap.shorten(text, width=3500, placeholder=" …")

# ---------- state
def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"last_seen": None, "queue_count": 0}

def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

def load_queue() -> list[str]:
    if QUEUE_FILE.exists():
        return [ln.rstrip("\n") for ln in QUEUE_FILE.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return []

def save_queue(lines: list[str]) -> None:
    QUEUE_FILE.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

# ---------- main
def main():
    state = load_state()
    cur = head()
    last = state.get("last_seen")

    # first run → initialize last_seen and exit (no spam)
    if not last:
        state["last_seen"] = cur
        state["queue_count"] = 0
        save_state(state)
        print("[auto_release] initialized (no prior state)")
        return

    new_subjects = subjects_between(last, cur)
    if not new_subjects:
        print("[auto_release] no new commits")
        return

    queue = load_queue()
    queue.extend(new_subjects)
    save_queue(queue)

    state["queue_count"] = int(state.get("queue_count", 0)) + len(new_subjects)
    state["last_seen"] = cur
    save_state(state)
    print(f"[auto_release] queued {len(new_subjects)} change(s); total {state['queue_count']}/{THRESHOLD}")

    if state["queue_count"] < THRESHOLD:
        return  # not time yet

    # Time to release: bump minor, compose notes from queue, reset
    old_v = read_version()
    new_v = bump_minor(old_v)
    VERSION_FILE.write_text(new_v, encoding="utf-8")

    body = compose_body(queue)
    # tack on a footer timestamp for traceability
    stamp = datetime.utcnow().strftime("*UTC %Y-%m-%d %H:%M*")
    NOTES_FILE.write_text(f"{body}\n\n_{stamp}_", encoding="utf-8")

    # reset queue & counter
    save_queue([])
    state["queue_count"] = 0
    save_state(state)
    print(f"[auto_release] RELEASED {old_v} ➜ {new_v} ({len(new_subjects)} new, {len(queue)} total in batch)")

if __name__ == "__main__":
    main()
