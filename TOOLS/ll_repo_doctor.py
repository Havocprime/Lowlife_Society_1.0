# tools/ll_repo_doctor.py
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class DirectoryIssue:
    kind: str
    details: str


def rel(root: Path, p: Path) -> str:
    try:
        return str(p.relative_to(root)).replace("\\", "/")
    except Exception:
        return str(p).replace("\\", "/")


def time_stamp() -> str:
    # ISO-like, safe for filenames
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def expected_checks(repo_root: Path) -> List[Tuple[str, Path]]:
    """Define the set of dirs we want to sanity-check exist."""
    return [
        ("src", repo_root / "src"),
        ("src.cogs", repo_root / "src" / "cogs"),
        ("src.cogs.tags", repo_root / "src" / "cogs" / "tags"),
        ("GAME.src", repo_root / "GAME" / "src"),
        ("GAME.src.cogs", repo_root / "GAME" / "src" / "cogs"),
        ("GAME.src.tags", repo_root / "GAME" / "src" / "tags"),
        ("GAME.src.cogs.tags", repo_root / "GAME" / "src" / "cogs" / "tags"),
    ]


def find_duplicate_game_dirs(repo_root: Path) -> List[DirectoryIssue]:
    issues: List[DirectoryIssue] = []
    nested = repo_root / "GAME" / "GAME"
    if nested.exists():
        issues.append(
            DirectoryIssue(
                "duplicate_dir",
                f"Nested GAME/GAME exists at: {rel(repo_root, nested)} â€” consider moving its contents up to GAME/ and removing the extra folder.",
            )
        )
    return issues


def find_multiple_tag_packages(repo_root: Path) -> List[DirectoryIssue]:
    """
    Look for multiple 'tags' packages that contain a Python module like cog.py.
    This catches the common duplication 'GAME/src/tags' vs 'GAME/src/cogs/tags'.
    """
    issues: List[DirectoryIssue] = []

    tag_dirs: List[Path] = []
    for p in repo_root.rglob("tags"):
        if p.is_dir():
            # consider it a real package if it has any .py file inside
            if any(pp.suffix == ".py" for pp in p.rglob("*.py")):
                tag_dirs.append(p)

    # unique parents
    unique_dirs = sorted(set(tag_dirs))
    if len(unique_dirs) > 1:
        pretty = "\n    ".join(rel(repo_root, d) for d in unique_dirs)
        issues.append(
            DirectoryIssue(
                "duplicate_package",
                "Multiple 'tags' packages found:\n"
                f"    {pretty}\n"
                "Recommended: Keep a single canonical package under GAME/src/cogs/tags "
                "and migrate others into it.",
            )
        )

    # Specific conflict: GAME/src/tags and GAME/src/cogs/tags both exist
    t1 = repo_root / "GAME" / "src" / "tags"
    t2 = repo_root / "GAME" / "src" / "cogs" / "tags"
    if t1.exists() and t2.exists():
        issues.append(
            DirectoryIssue(
                "conflict_paths",
                f"Both {rel(repo_root, t1)} and {rel(repo_root, t2)} exist. "
                "Use GAME/src/cogs/tags as the canonical location.",
            )
        )

    return issues


def write_files(repo_root: Path, report: Dict) -> List[Path]:
    audit_dir = repo_root / ".repo_audit"
    audit_dir.mkdir(exist_ok=True)

    ts = time_stamp()
    json_path = audit_dir / f"doctor-report-{ts}.json"
    md_path = audit_dir / f"doctor-report-{ts}.md"
    ps1_path = audit_dir / f"doctor-moves-{ts}.ps1"

    # JSON
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    # Markdown summary
    md = ["# Repo Doctor Report", "", f"_Generated: {ts}Z_", ""]
    md.append("## Quick Summary")
    md.append("")
    md.append(f"Files scanned: {report.get('files_scanned', 0)}")
    md.append("")
    md.append("### Checks")
    for name, status in report.get("checks", {}).items():
        md.append(f"- **{name}**: `{status}`")
    md.append("")
    issues = report.get("directory_issues", [])
    if issues:
        md.append("### Directory Issues")
        for i in issues:
            if isinstance(i, dict):
                kind = i.get("kind", "unknown")
                details = i.get("details", "")
            else:
                kind = getattr(i, "kind", type(i).__name__)
                details = getattr(i, "details", repr(i))
            md.append(f"- **{kind}** â€” {details}")
    else:
        md.append("### Directory Issues")
        md.append("- None ðŸŽ‰")
    md_path.write_text("\n".join(md), encoding="utf-8")

    # PS1: scaffold for future move commands (keeps it harmless by default)
    ps1_body = textwrap.dedent(f"""
        # Generated move helper â€” {ts}
        # Review, then uncomment the commands you want to run.

        # Example: move 'GAME/src/tags' into 'GAME/src/cogs/tags'
        # robocopy "GAME\\src\\tags" "GAME\\src\\cogs\\tags" /E /MOVE
        # git add -A
        # git commit -m "Consolidate tags package into GAME/src/cogs/tags"
    """).lstrip()
    ps1_path.write_text(ps1_body, encoding="utf-8")

    return [json_path, md_path, ps1_path]


def scan_file_count(repo_root: Path) -> int:
    count = 0
    for p in repo_root.rglob("*"):
        try:
            if p.is_file():
                count += 1
        except PermissionError:
            pass
    return count


def main() -> None:
    # repo_root = tools/..  (this file lives in tools/)
    repo_root = Path(__file__).resolve().parents[1]

    # Build basic checks
    checks: Dict[str, str] = {}
    for label, p in expected_checks(repo_root):
        checks[label] = "OK" if p.exists() else "MISSING"

    # Issues
    issues: List[DirectoryIssue] = []
    issues.extend(find_duplicate_game_dirs(repo_root))
    issues.extend(find_multiple_tag_packages(repo_root))

    # Assemble report
    report: Dict = {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "files_scanned": scan_file_count(repo_root),
        "checks": checks,
        "directory_issues": [asdict(i) for i in issues],
        "repo_root": str(repo_root),
    }

    # Write artifacts
    written = write_files(repo_root, report)

    # Console output
    for p in written:
        print(f"WROTE: {p}")

    print("\n=== QUICK SUMMARY ===")
    print(f"Files scanned: {report['files_scanned']}")
    print("")
    # A few key checks that help orientation
    for name in ["src", "src.cogs", "src.cogs.tags", "GAME.src", "GAME.src.cogs", "GAME.src.tags", "GAME.src.cogs.tags"]:
        if name in checks:
            print(f"{name:15}: {checks[name]}")

    # --- Pretty-print directory issues (INSIDE main!) ---
    dir_issues = report.get("directory_issues", [])
    if dir_issues:
        print("\nDirectory issues:")
        for i in dir_issues:
            if isinstance(i, dict):
                kind = i.get("kind", "unknown")
                details = i.get("details", "")
            else:
                kind = getattr(i, "kind", type(i).__name__)
                details = getattr(i, "details", repr(i))
            print(f"  - {kind}: {details}")
    else:
        print("\nDirectory issues: none \N{party popper}")


if __name__ == "__main__":
    main()
