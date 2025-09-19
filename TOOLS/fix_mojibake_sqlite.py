from __future__ import annotations
import argparse, pathlib, shutil, sqlite3, time
from typing import Iterable

# same cleaner as above
def _utf8_clean(s: str | None) -> str | None:
    if not isinstance(s, str) or not s: return s
    s = s.replace("\u00A0", " ")
    if all(ord(ch) < 128 for ch in s): return s
    markers = ("Ã","Â","â","ð","€","™","œ","š","ž")
    if not any(m in s for m in markers): return s
    for enc in ("cp1252","latin1"):
        try:
            fixed = s.encode(enc,"strict").decode("utf-8")
            if any(m in fixed for m in markers):
                try:
                    return fixed.encode(enc,"strict").decode("utf-8")
                except Exception:
                    return fixed
            return fixed
        except Exception:
            continue
    return s

def quote(name: str) -> str:
    return '"' + name.replace('"','""') + '"'

def text_columns(cur: sqlite3.Cursor, table: str) -> list[str]:
    cols = []
    for cid, name, ctype, notnull, dflt, pk in cur.execute(f"PRAGMA table_info({quote(table)})"):
        t = (ctype or "").upper()
        if "TEXT" in t or "CHAR" in t or "CLOB" in t:
            cols.append(name)
    return cols

def fix_db(path: pathlib.Path, apply: bool) -> tuple[int, int]:
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL")
    changed_rows = 0
    changed_cells = 0

    tables = [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    for t in tables:
        cols = text_columns(cur, t)
        if not cols: continue
        sel = f"SELECT rowid, {', '.join(quote(c) for c in cols)} FROM {quote(t)}"
        for row in cur.execute(sel):
            rowid, *vals = row
            new_vals = []
            dirty = False
            for v in vals:
                nv = _utf8_clean(v)
                new_vals.append(nv)
                if nv != v:
                    dirty = True
                    changed_cells += 1
            if dirty and apply:
                sets = ", ".join(f"{quote(c)}=?" for c in cols)
                cur.execute(f"UPDATE {quote(t)} SET {sets} WHERE rowid=?", (*new_vals, rowid))
                changed_rows += 1

    if apply:
        conn.commit()
    conn.close()
    return changed_rows, changed_cells

def walk_sqlites(root: pathlib.Path) -> Iterable[pathlib.Path]:
    for p in root.rglob("*.sqlite"):
        yield p

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("root", nargs="?", default=".")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    total_rows = total_cells = 0
    for db in walk_sqlites(root):
        print(f"[db] scanning {db}")
        if args.apply:
            backup = db.with_suffix(db.suffix + f".bak.{int(time.time())}")
            shutil.copy2(db, backup)
            print(f"      backup -> {backup.name}")
        rows, cells = fix_db(db, args.apply)
        print(f"      fixed rows={rows}, cells={cells}")
        total_rows += rows; total_cells += cells

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"[done] {mode}: total_rows={total_rows}, total_cells={total_cells}")

if __name__ == "__main__":
    main()
