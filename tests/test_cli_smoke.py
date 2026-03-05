from __future__ import annotations

import io
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


def test_cli_dry_run_color_never_outputs_plain_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    rc = main([str(current), "--by", str(extension), "--dry-run", "--color", "never"])
    assert rc == 0

    captured = capsys.readouterr()
    assert captured.out == "a: 1\nb: 2\n"
    assert "\x1b[" not in captured.out


def test_cli_dry_run_color_always_forces_ansi(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    rc = main([str(current), "--by", str(extension), "--dry-run", "--color", "always"])
    assert rc == 0

    captured = capsys.readouterr()
    assert "\x1b[" in captured.out


def test_cli_dry_run_color_auto_uses_ansi_on_tty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    rc = main([str(current), "--by", str(extension), "--dry-run", "--color", "auto"])
    assert rc == 0

    captured = capsys.readouterr()
    assert "\x1b[" in captured.out


def test_cli_dry_run_color_auto_outputs_plain_text_on_non_tty(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    monkeypatch.setattr("sys.stdout.isatty", lambda: False)

    rc = main([str(current), "--by", str(extension), "--dry-run", "--color", "auto"])
    assert rc == 0

    captured = capsys.readouterr()
    assert captured.out == "a: 1\nb: 2\n"
    assert "\x1b[" not in captured.out


def test_cli_allow_overwrite_requires_overwrite_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 2\n", encoding="utf-8")

    rc = main([str(current), "--by", str(extension), "--dry-run", "--allow-overwrite"])
    assert rc == 2

    captured = capsys.readouterr()
    assert "--allow-overwrite requires at least one --overwrite-path" in captured.err


def test_cli_overwrite_path_requires_allow_overwrite(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 2\n", encoding="utf-8")

    rc = main([str(current), "--by", str(extension), "--dry-run", "--overwrite-path", "/a"])
    assert rc == 2

    captured = capsys.readouterr()
    assert "--overwrite-path requires --allow-overwrite" in captured.err


def test_cli_dry_run_order_by_extension_reorders_keys(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("b: 1\na: 1\nc: 1\n", encoding="utf-8")
    extension.write_text("a: 9\nb: 8\nd: 4\n", encoding="utf-8")

    rc = main(
        [
            str(current),
            "--by",
            str(extension),
            "--dry-run",
            "--color",
            "never",
            "--order-by",
            "extension",
        ]
    )
    assert rc == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines.index("a: 1") < lines.index("b: 1") < lines.index("d: 4") < lines.index("c: 1")


def test_cli_dry_run_by_dash_reads_extension_from_stdin(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current = tmp_path / "current.yaml"
    current.write_text("a: 1\n", encoding="utf-8")

    monkeypatch.setattr("sys.stdin", io.StringIO("a: 1\nb: 2\n"))

    rc = main([str(current), "--by", "-", "--dry-run", "--color", "never"])
    assert rc == 0

    captured = capsys.readouterr()
    assert captured.out == "a: 1\nb: 2\n"


def test_cli_dry_run_applies_multiple_by_in_order(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = tmp_path / "current.yaml"
    ext1 = tmp_path / "ext1.yaml"
    ext2 = tmp_path / "ext2.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    ext1.write_text("a: 1\nb: 2\n", encoding="utf-8")
    ext2.write_text("a: 1\nb: 2\nc: 3\n", encoding="utf-8")

    rc = main(
        [
            str(current),
            "--by",
            str(ext1),
            "--by",
            str(ext2),
            "--dry-run",
            "--color",
            "never",
        ]
    )
    assert rc == 0

    captured = capsys.readouterr()
    assert captured.out == "a: 1\nb: 2\nc: 3\n"


def test_cli_dry_run_skip_missing_keys_does_not_add_new_mapping_key(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    rc = main(
        [
            str(current),
            "--by",
            str(extension),
            "--dry-run",
            "--color",
            "never",
            "--skip-missing-keys",
        ]
    )
    assert rc == 0

    captured = capsys.readouterr()
    assert captured.out == "a: 1\n"
