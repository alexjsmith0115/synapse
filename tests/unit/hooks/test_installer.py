"""Tests for hook script installer."""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


class TestInstallScripts:
    def test_creates_hooks_directory(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        install_scripts(hooks_dir)

        assert hooks_dir.is_dir()

    def test_writes_all_four_scripts(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        install_scripts(hooks_dir)

        assert (hooks_dir / "common.sh").exists()
        assert (hooks_dir / "claude-gate.sh").exists()
        assert (hooks_dir / "cursor-gate.sh").exists()
        assert (hooks_dir / "copilot-gate.sh").exists()

    def test_scripts_are_executable(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        install_scripts(hooks_dir)

        for name in ("common.sh", "claude-gate.sh", "cursor-gate.sh", "copilot-gate.sh"):
            mode = (hooks_dir / name).stat().st_mode
            assert mode & stat.S_IXUSR, f"{name} should be user-executable"

    def test_skips_existing_scripts_without_force(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        install_scripts(hooks_dir)

        sentinel = hooks_dir / "common.sh"
        sentinel.write_text("# user-modified\n")

        install_scripts(hooks_dir, force=False)
        assert sentinel.read_text() == "# user-modified\n"

    def test_overwrites_existing_scripts_with_force(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        install_scripts(hooks_dir)

        sentinel = hooks_dir / "common.sh"
        sentinel.write_text("# user-modified\n")

        install_scripts(hooks_dir, force=True)
        assert sentinel.read_text() != "# user-modified\n"

    def test_returns_list_of_written_files(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        written = install_scripts(hooks_dir)

        assert len(written) == 4
        assert all(isinstance(p, Path) for p in written)


class TestRemoveScripts:
    def test_removes_hooks_directory(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import install_scripts, remove_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        install_scripts(hooks_dir)
        remove_scripts(hooks_dir)

        assert not hooks_dir.exists()

    def test_noop_if_directory_missing(self, tmp_path: Path) -> None:
        from synapps.hooks.installer import remove_scripts

        hooks_dir = tmp_path / ".synapps" / "hooks"
        remove_scripts(hooks_dir)  # should not raise
