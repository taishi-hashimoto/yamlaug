from __future__ import annotations

import codecs
from pathlib import Path

import pytest

from yamlaug.file_api import augment_file


def test_augment_file_preserves_crlf_newline(tmp_path: Path) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_bytes(b"a: 1\r\n")
    extension.write_bytes(b"a: 1\r\nb: 2\r\n")

    report = augment_file(current, extension, backup=False, atomic=True)
    assert report.changed is True

    data = current.read_bytes()
    assert b"\r\n" in data
    assert b"\n" not in data.replace(b"\r\n", b"")


def test_augment_file_preserves_utf8_bom(tmp_path: Path) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_bytes(codecs.BOM_UTF8 + "a: 1\n".encode("utf-8"))
    extension.write_bytes(codecs.BOM_UTF8 + "a: 1\nb: 2\n".encode("utf-8"))

    report = augment_file(current, extension, backup=False, atomic=True)
    assert report.changed is True

    output = current.read_bytes()
    assert output.startswith(codecs.BOM_UTF8)


def test_augment_file_detects_non_utf8_encoding_and_preserves(tmp_path: Path) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current_text = "name: 太郎次郎三郎花子\ndesc: 日本語の設定値を複数含むテキストです\n"
    extension_text = (
        "name: 太郎次郎三郎花子\n"
        "desc: 日本語の設定値を複数含むテキストです\n"
        "city: 大阪府大阪市\n"
    )

    current.write_bytes(current_text.encode("cp932"))
    extension.write_bytes(extension_text.encode("cp932"))

    report = augment_file(current, extension, backup=False, atomic=True)
    assert report.changed is True

    output = current.read_bytes()
    decoded = output.decode("cp932")
    assert "city: 大阪府大阪市" in decoded


def test_augment_file_raises_on_encoding_detection_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_bytes(b"a: 1\n")
    extension.write_bytes(b"a: 1\nb: 2\n")

    import yamlaug.io as io_module

    def _raise_detection(_: bytes) -> str:
        raise ValueError("failed to detect file encoding")

    monkeypatch.setattr(io_module, "_detect_encoding", _raise_detection)

    with pytest.raises(ValueError, match="failed to detect file encoding"):
        augment_file(current, extension, backup=False, atomic=True)


def test_augment_file_raises_when_uid_gid_apply_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    import yamlaug.file_api as file_api_module

    def _raise_chown(path: str, uid: int, gid: int) -> None:  # type: ignore[unused-argument]
        raise PermissionError("cannot apply uid/gid")

    monkeypatch.setattr(file_api_module.os, "chown", _raise_chown)

    with pytest.raises(PermissionError, match="cannot apply uid/gid"):
        augment_file(current, extension, backup=False, atomic=True)


def test_augment_file_preserves_mode_bits(tmp_path: Path) -> None:
    current = tmp_path / "current.yaml"
    extension = tmp_path / "extension.yaml"

    current.write_text("a: 1\n", encoding="utf-8")
    extension.write_text("a: 1\nb: 2\n", encoding="utf-8")

    current.chmod(0o640)

    report = augment_file(current, extension, backup=False, atomic=True)
    assert report.changed is True
    assert (current.stat().st_mode & 0o777) == 0o640
