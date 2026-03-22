from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GitDiff:
    to_delete: set[str] = field(default_factory=set)
    to_reindex: set[str] = field(default_factory=set)
    renames: list[tuple[str, str]] = field(default_factory=list)


def is_git_repo(root_path: str) -> bool:
    return (Path(root_path) / ".git").is_dir()


def rev_parse_head(root_path: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root_path,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _diff_name_status(
    root_path: str, ref_spec: str | None
) -> list[tuple[str, str, str | None]]:
    cmd = ["git", "diff", "--name-status"]
    if ref_spec == "--cached":
        cmd.append("--cached")
    elif ref_spec is not None:
        cmd.append(ref_spec)

    result = subprocess.run(cmd, cwd=root_path, capture_output=True, text=True)
    if result.returncode != 0:
        return []

    entries: list[tuple[str, str, str | None]] = []
    for line in result.stdout.strip().splitlines():
        parts = line.split("\t")
        status = parts[0]
        if status.startswith(("R", "C")):
            entries.append((status, parts[1], parts[2]))
        else:
            entries.append((status, parts[1], None))
    return entries


def compute_git_diff(root_path: str, stored_sha: str) -> GitDiff:
    committed = _diff_name_status(root_path, f"{stored_sha}..HEAD")
    unstaged = _diff_name_status(root_path, None)
    staged = _diff_name_status(root_path, "--cached")

    diff = GitDiff()

    for status, old_path, new_path in committed + unstaged + staged:
        if status == "D":
            diff.to_delete.add(os.path.join(root_path, old_path))
        elif status.startswith("R") or status.startswith("C"):
            abs_old = os.path.join(root_path, old_path)
            abs_new = os.path.join(root_path, new_path)  # type: ignore[arg-type]
            if status.startswith("R"):
                diff.renames.append((abs_old, abs_new))
            diff.to_reindex.add(abs_new)
        else:
            # A, M, T, and any other status
            diff.to_reindex.add(os.path.join(root_path, old_path))

    # Renamed files should not appear in to_delete
    for old, _new in diff.renames:
        diff.to_delete.discard(old)

    return diff
