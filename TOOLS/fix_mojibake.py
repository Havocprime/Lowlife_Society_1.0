# tools/fix_mojibake.py
# Dry run:  python tools/fix_mojibake.py
# Apply:    python tools/fix_mojibake.py --apply

from __future__ import annotations
import argparse, json, shutil, sqlite3, sys
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[1]
GAME = REPO / "GAME"
DB_DIRS = [GAME / "db", GAME / "data", REPO / ".repo_archive"]

TEXT_EXTS = {".py",".txt",".md",".sql",".json",".yml",".yaml",".ini",".cfg",".toml",".csv"}
BAD_MARKERS = ("Ã", "Â", "â", "\ufffd")  # \ufffd = replacement char

def looks_baked(s: str) -> bool:
    return any(m in s for m in BAD_MARKERS)

def demojibake(s: str) -> str:
    """Fix common mojibake: cp1252/latin1 ←→ utf-8 and NBSPs."""
    if not isinstance(s, str) or not s:
        return s
    s = s.replace("\xa0", " ")  # NBSP → space
    # First try cp1252 route (fixes â”€ â€¢ Â etc.)
    if looks_baked(s):
        try:
            s2 = s.encode("cp1252").decode("utf-8")
            s = s2
        except Exception:
            pass
    # Fallback: latin1 route (handles Ã© → é, etc.)
    if looks_baked(s):
        try:
            s2 = s.encode("latin1").decode("utf-8")
            s = s2
        except Exception:
            pass
    return s

def deep_fix_json(val):
    if isinstance(val, dict):
        return {deep_fix_json(k): deep_fix_json(v) for k, v in val.items()}
    if isinstance(val, list):
        return [deep_fix_json(v) for v in val]
    if isinstance(val, str):
        return demojibake(val)
    return val

def qident(name: str) -> str:
    return "rowid" if name.lower()=="rowid" else '"' + name.replace('"','""') + '"'

def fix_text_files(root: Path, apply: bool) -> tuple[int,int]:
    changed = scanned = 0
    for p in root.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in TEXT_EXTS:
            continue
        scanned += 1
        try:
            try:
                raw = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                raw = p.read_text(encoding="latin-1")
            fixed = demojibake(raw)
            if fixed != raw or looks_baked(raw):
                changed += 1
                if apply:
                    p.write_text(fixed, encoding="utf-8", newline="\n")
        except Exception as e:
            print(f"[files] skip {p}: {e}")
    return changed, scanned

def find_sqlite_dbs() -> list[Path]:
    found: list[Path] = []
    for d in DB_DIRS:
        if d.exists():
            found += list(d.rglob("*.sqlite"))
    for p in REPO.rglob("*.sqlite"):
        if p not in found:
            found.append(p)
    return found

def get_text_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    cols = cur.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    out = []
    for c in cols:                 # (cid,name,type,notnull,dflt,pk)
        name, ctype = c[1], (c[2] or "").upper()
        if ("TEXT" in ctype) or ("CHAR" in ctype) or ("CLOB" in ctype) or (ctype == ""):
            out.append(name)
    return out

def get_key_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    cols = cur.execute(f"PRAGMA table_info({qident(table)})").fetchall()
    pk = [c[1] for c in cols if (c[5] or 0) > 0]
    if pk:
        return pk
    try:
        cur.execute(f"SELECT rowid FROM {qident(table)} LIMIT 1")
        return ["rowid"]
    except Exception:
        return []

def fix_one_db(db_path: Path, apply: bool) -> tuple[int,int]:
    print(f"[db] scanning {db_path}")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    total_updates = total_rows = 0
    try:
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        for t in tables:
            if t.startswith("sqlite_"):  # internal tables
                continue
            text_cols = get_text_columns(cur, t)
            if not text_cols:
                continue
            key_cols = get_key_columns(cur, t)
            if not key_cols:
                print(f"[db]  - {t}: skip (no PK and no rowid)")
                continue
            sel = ", ".join(qident(c) for c in key_cols + text_cols)
            rows = cur.execute(f"SELECT {sel} FROM {qident(t)}").fetchall()
            for r in rows:
                total_rows += 1
                key_vals = [r[c] for c in key_cols]
                old_vals = [r[c] for c in text_cols]
                new_vals, dirty = [], False
                for v in old_vals:
                    if v is None:
                        new_vals.append(v); continue
                    if isinstance(v, (bytes, bytearray)):
                        try: v = v.decode("utf-8")
                        except Exception: v = v.decode("cp1252", "ignore")
                    if isinstance(v, str):
                        fixed = demojibake(v)
                        v2 = fixed
                        s = fixed.strip()
                        if (s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]")):
                            try:
                                obj = json.loads(fixed)
                                obj2 = deep_fix_json(obj)
                                v2 = json.dumps(obj2, ensure_ascii=False)
                            except Exception:
                                pass
                        if v2 != v:
                            dirty = True
                            new_vals.append(v2)
                        else:
                            new_vals.append(v)
                    else:
                        new_vals.append(v)
                if dirty and apply:
                    set_clause = ", ".join(f"{qident(c)}=?" for c in text_cols)
                    where_clause = " AND ".join(f"{qident(c)}=?" for c in key_cols)
                    cur.execute(
                        f"UPDATE {qident(t)} SET {set_clause} WHERE {where_clause}",
                        (*new_vals, *key_vals),
                    )
                    total_updates += 1
        if apply:
            conn.commit()
    finally:
        conn.close()
    return total_updates, total_rows

def backup_db(db_path: Path):
    dst = db_path.with_suffix(db_path.suffix + ".bak")
    shutil.copy2(db_path, dst)
    print(f"[db] backup -> {dst.name}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    args = ap.parse_args()

    print(f"[info] repo: {REPO}")
    print("[info] DRY RUN" if not args.apply else "[info] APPLYING changes")

    changed, scanned = fix_text_files(REPO, args.apply)
    print(f"[files] scanned: {scanned}  would_change: {changed}")

    dbs = find_sqlite_dbs()
    if not dbs:
        print("[db] no .sqlite files found")
    total_u = total_r = 0
    for db in dbs:
        if args.apply: backup_db(db)
        u, r = fix_one_db(db, args.apply)
        total_u += u; total_r += r
    print(f"[db] rows scanned: {total_r}  rows updated: {total_u}")
    print("\nDone. Restart your bot and re-check Discord.")

if __name__ == "__main__":
    import os
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    main()
