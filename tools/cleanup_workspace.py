#!/usr/bin/env python3
"""Clean regenerable workspace artifacts without touching user data.

The default is a dry run.  Deletion requires an explicit ``--apply``.

Profiles
--------
safe
    pytest output, Python bytecode caches, and regenerable Nuitka caches.
builds
    ``safe`` plus historical build directories.  The newest version keeps
    its OneFile output; an unpacked StandAlone directory is removed only when
    a matching ZIP archive already exists.
deep
    ``builds`` plus the known intermediate experiment outputs under
    ``.opencode_cache``.  Review the dry-run output before applying this.

Examples
--------
python tools/cleanup_workspace.py --profile safe
python tools/cleanup_workspace.py --profile safe --apply
python tools/cleanup_workspace.py --profile builds --apply
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
VERSION_DIR_RE = re.compile(r"^CVAnalysis_(OneFile|StandAlone)_v(\d+(?:\.\d+)*)$")
STANDALONE_ZIP_RE = re.compile(r"^CVAnalysis_StandAlone_v(\d+(?:\.\d+)*)\.zip$")
SKIP_PYCACHE_ROOTS = {".git", ".opencode_cache", "build_cache", ".test_tmp", ".local"}
USER_DATA_NAMES = {
    "config.json",
    "themes.json",
    "CP-Test.txt",
    "P1.cvproj",
    "CP.cvproj",
    "CP-T.cvproj",
    "CV-SR-4.cvproj",
    "CV-Voltage.cvproj",
    "EIS-Test.cvproj",
    "I-T.cvproj",
    "LSV.cvproj",
    "README.md",
    "README_LOCAL.md",
    "Build.md",
    "DESIGN.md",
    "Vibe_Coding_Outline.md",
}
SAFE_BUILD_CACHE_DIRS = (
    "build_cache/clcache",
    "build_cache/module-cache",
    "build_cache/downloads",
    "build_cache/library_dependencies",
    "build_cache/scons-msvc-config",
    "build_cache/updates",
)
DEEP_TARGETS = (
    ".opencode_cache/glass_demo/liquid_experiment",
    ".opencode_cache/glass_demo/screenshots/matrix",
    ".opencode_cache/glass_demo/screenshots/snapshot",
    ".opencode_cache/glass_demo/screenshots/opaque",
    ".opencode_cache/main_gui_liquid_demo/output/capture-debug",
    ".opencode_cache/main_gui_liquid_demo/output/empty-balanced",
    ".opencode_cache/main_gui_liquid_demo/output/empty-check",
    ".opencode_cache/main_gui_liquid_demo/output/empty-solid",
    ".opencode_cache/main_gui_liquid_demo/output/empty-solid-check",
    ".opencode_cache/main_gui_liquid_demo/output/history",
    ".opencode_cache/mainline_migration_baseline/compatibility-output",
)


@dataclass
class Candidate:
    path: Path
    reason: str
    size: int = 0


def is_reparse_point(path: Path) -> bool:
    """Return True for symlinks, junctions and other Windows reparse points."""
    try:
        info = os.lstat(path)
    except OSError:
        return False
    if os.path.islink(path):
        return True
    if hasattr(os.path, "isjunction") and os.path.isjunction(path):
        return True
    attrs = getattr(info, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    return bool(attrs & reparse_flag)


def remove_reparse_point(path: Path) -> None:
    """Remove a link/junction itself, never its target."""
    try:
        if is_reparse_point(path) and path.is_dir() and not path.is_symlink():
            os.rmdir(path)
        else:
            os.unlink(path)
    except PermissionError:
        # Windows directory symlinks are removed with rmdir.
        os.rmdir(path)


def path_size(path: Path) -> int:
    """Return size without following reparse points."""
    if is_reparse_point(path):
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for current, dirs, files in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for name in dirs:
            child = current_path / name
            if is_reparse_point(child):
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in files:
            child = current_path / name
            if is_reparse_point(child):
                continue
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def remove_tree_safely(path: Path) -> None:
    """Remove a tree while unlinking nested reparse points first."""
    if is_reparse_point(path):
        remove_reparse_point(path)
        return
    if not path.is_dir():
        try:
            path.unlink()
        except PermissionError:
            os.chmod(path, stat.S_IWRITE)
            path.unlink()
        return

    for current, dirs, files in os.walk(path, topdown=True, followlinks=False):
        current_path = Path(current)
        kept_dirs: list[str] = []
        for name in dirs:
            child = current_path / name
            if is_reparse_point(child):
                remove_reparse_point(child)
            else:
                kept_dirs.append(name)
        dirs[:] = kept_dirs
        for name in files:
            child = current_path / name
            if is_reparse_point(child):
                remove_reparse_point(child)

    def handle_error(func, target, exc_info):  # noqa: ANN001 - shutil API
        try:
            os.chmod(target, stat.S_IWRITE)
            func(target)
        except OSError:
            raise exc_info[1]

    try:
        shutil.rmtree(path, onerror=handle_error)
    except OSError:
        # An inaccessible child should not block cleanup of its siblings.
        errors: list[OSError] = []
        for child in path.iterdir():
            try:
                remove_tree_safely(child)
            except OSError as exc:
                errors.append(exc)
        if errors:
            raise errors[0]
        path.rmdir()


def parse_version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def versioned_build_dirs() -> dict[str, dict[str, Path]]:
    versions: dict[str, dict[str, Path]] = {}
    for child in ROOT.iterdir():
        if not child.is_dir() or is_reparse_point(child):
            continue
        match = VERSION_DIR_RE.match(child.name)
        if not match:
            continue
        kind, version = match.groups()
        versions.setdefault(version, {})[kind] = child
    return versions


def find_pycache_dirs(skip_roots: set[str] | None = None) -> list[Path]:
    found: list[Path] = []
    skipped = SKIP_PYCACHE_ROOTS if skip_roots is None else skip_roots

    def walk(directory: Path) -> None:
        try:
            entries = list(os.scandir(directory))
        except OSError:
            return
        for entry in entries:
            child = Path(entry.path)
            if not entry.is_dir(follow_symlinks=False):
                continue
            if entry.name in skipped or is_reparse_point(child):
                continue
            if entry.name == "__pycache__":
                found.append(child)
                continue
            walk(child)

    walk(ROOT)
    return found


def safe_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    for relative in (".test_tmp", ".pytest_cache", *SAFE_BUILD_CACHE_DIRS):
        path = ROOT / relative
        if path.exists():
            candidates.append(Candidate(path, "regenerable cache"))
    for path in find_pycache_dirs():
        candidates.append(Candidate(path, "Python bytecode cache"))
    return candidates


def builds_candidates(
    keep_latest: int, keep_unpacked_standalone: bool
) -> list[Candidate]:
    candidates: list[Candidate] = []
    versions = versioned_build_dirs()
    archives: dict[str, Path] = {}
    for child in ROOT.iterdir():
        match = STANDALONE_ZIP_RE.match(child.name)
        if match and child.is_file() and not is_reparse_point(child):
            archives[match.group(1)] = child

    ordered = sorted(set(versions) | set(archives), key=parse_version)
    if not ordered:
        return candidates

    keep = set(ordered[-keep_latest:])
    for version in ordered:
        if version in keep:
            continue
        for kind, path in sorted(versions.get(version, {}).items()):
            candidates.append(Candidate(path, f"historical build v{version}"))
        archive = archives.get(version)
        if archive is not None:
            candidates.append(Candidate(archive, f"historical StandAlone ZIP v{version}"))

    for version in sorted(keep, key=parse_version):
        standalone = versions.get(version, {}).get("StandAlone")
        archive = ROOT / f"CVAnalysis_StandAlone_v{version}.zip"
        if (
            standalone is not None
            and archive.is_file()
            and not keep_unpacked_standalone
        ):
            candidates.append(
                Candidate(
                    standalone,
                    f"unpacked StandAlone v{version} superseded by {archive.name}",
                )
            )
    return candidates


def deep_candidates() -> list[Candidate]:
    candidates: list[Candidate] = []
    for relative in DEEP_TARGETS:
        path = ROOT / relative
        if path.exists():
            candidates.append(Candidate(path, "intermediate experiment output"))
    opencode_cache = ROOT / ".opencode_cache"
    skip_for_deep = {".git", "build_cache", ".test_tmp", ".local"}
    for path in find_pycache_dirs(skip_roots=skip_for_deep):
        try:
            path.relative_to(opencode_cache)
        except ValueError:
            continue
        candidates.append(Candidate(path, "experiment bytecode cache"))
    return candidates


def validate(candidate: Candidate) -> None:
    path = candidate.path.resolve()
    try:
        path.relative_to(ROOT)
    except ValueError as exc:
        raise ValueError(f"target is outside the workspace: {path}") from exc

    if path == ROOT:
        raise ValueError("refusing to delete the workspace root")
    if path.name in USER_DATA_NAMES:
        raise ValueError(f"refusing to delete protected user data: {path}")
    if path.suffix.lower() == ".cvproj":
        raise ValueError(f"refusing to delete a user project: {path}")
    try:
        path.relative_to(ROOT / "testdata")
    except ValueError:
        pass
    else:
        raise ValueError(f"refusing to delete test data: {path}")

    if candidate.reason == "intermediate experiment output":
        try:
            path.relative_to(ROOT / ".opencode_cache")
        except ValueError as exc:
            raise ValueError(f"deep target is outside .opencode_cache: {path}") from exc


def deduplicate(candidates: Iterable[Candidate]) -> list[Candidate]:
    result: list[Candidate] = []
    kept: list[Path] = []
    ordered = sorted(candidates, key=lambda item: len(item.path.resolve().parts))
    for candidate in ordered:
        resolved = candidate.path.resolve()
        if any(resolved == root or root in resolved.parents for root in kept):
            continue
        kept.append(resolved)
        candidate.size = path_size(candidate.path)
        result.append(candidate)
    return sorted(result, key=lambda item: str(item.path).lower())


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.2f} {unit}"
        value /= 1024
    return f"{value:.2f} TB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Clean regenerable CVAnalysis workspace artifacts."
    )
    parser.add_argument(
        "--profile",
        choices=("safe", "builds", "deep"),
        default="safe",
        help="cleanup scope (default: safe)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete; without this flag the command is a dry run",
    )
    parser.add_argument(
        "--keep-latest",
        type=int,
        default=1,
        metavar="N",
        help="number of newest build versions to keep (default: 1)",
    )
    parser.add_argument(
        "--keep-unpacked-standalone",
        action="store_true",
        help="do not remove the newest unpacked StandAlone directory",
    )
    args = parser.parse_args(argv)

    if args.keep_latest < 1:
        parser.error("--keep-latest must be at least 1")

    candidates: list[Candidate] = []
    if args.profile in {"safe", "builds", "deep"}:
        candidates.extend(safe_candidates())
    if args.profile in {"builds", "deep"}:
        candidates.extend(
            builds_candidates(
                keep_latest=args.keep_latest,
                keep_unpacked_standalone=args.keep_unpacked_standalone,
            )
        )
    if args.profile == "deep":
        candidates.extend(deep_candidates())

    candidates = deduplicate(candidates)
    for candidate in candidates:
        validate(candidate)

    mode = "APPLY" if args.apply else "DRY RUN"
    print(f"Workspace : {ROOT}")
    print(f"Profile   : {args.profile} ({mode})")
    print()

    total = 0
    reclaimed = 0
    errors: list[str] = []
    for candidate in candidates:
        total += candidate.size
        relative = candidate.path.relative_to(ROOT)
        if not args.apply:
            print(f"[DELETE] {human_size(candidate.size):>10}  {relative}  ({candidate.reason})")
            continue
        try:
            remove_tree_safely(candidate.path)
            reclaimed += candidate.size
            print(f"[DELETED] {human_size(candidate.size):>9}  {relative}")
        except OSError as exc:
            remaining = path_size(candidate.path) if candidate.path.exists() else 0
            freed = max(0, candidate.size - remaining)
            reclaimed += freed
            errors.append(f"{relative}: {exc}")
            print(
                f"[PARTIAL] {human_size(freed):>9}  {relative}  "
                f"(remaining {human_size(remaining)}; {exc})"
            )

    print()
    if args.apply:
        print(f"Reclaimed: {human_size(reclaimed)}")
        if errors:
            print(f"Failures : {len(errors)}")
            for error in errors:
                print(f"  - {error}")
            return 1
        print("All selected artifacts were removed.")
    else:
        print(f"Potential reclaim: {human_size(total)}")
        print("Nothing deleted. Re-run with --apply to remove these paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
