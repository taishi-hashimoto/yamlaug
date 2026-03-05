from __future__ import annotations

from pathlib import Path

import pytest

from yamlaug.cli import main


def test_cli_check_exit_codes(tmp_path: Path) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    rc_changed = main([str(current), "--by", str(extension), "--check"])
    assert rc_changed == 1

    current.write_text("a: 1\nb: 2\n", encoding="utf-8")
    rc_same = main([str(current), "--by", str(extension), "--check"])
    assert rc_same == 0


def test_cli_under_check_and_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a:\n  x: 1\n", encoding="utf-8")
    extension.write_text("a:\n  x: 1\n  y: 2\n", encoding="utf-8")

    rc_under_changed = main([str(current), "--by", str(extension), "--under", "/a", "--check"])
    assert rc_under_changed == 1

    rc_under_error = main([str(current), "--by", str(extension), "--under", "/missing", "--check"])
    assert rc_under_error == 2

    captured = capsys.readouterr()
    assert "yamlaug error: key not found: missing" in captured.err
