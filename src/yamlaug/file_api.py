from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from .core import augment_text
from .io import FileStatMeta, TextFormatMeta, encode_text_for_write, load_text_file
from .types import Report


def _timestamp_suffix() -> str:
    return datetime.now(timezone.utc).strftime(".%Y%m%d%H%M%S%fZ")


def _apply_stat(path: Path, *, stat_meta: FileStatMeta) -> None:
    path.chmod(stat_meta.mode)
    os.chown(path, stat_meta.uid, stat_meta.gid)


def _atomic_write(path: Path, content: bytes, *, stat_meta: FileStatMeta) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("wb", dir=path.parent, delete=False) as temp:
        temp.write(content)
        temp_name = temp.name

    temp_path = Path(temp_name)
    _apply_stat(temp_path, stat_meta=stat_meta)
    temp_path.replace(path)


def write_augmented_text(
    current_path: str | Path,
    augmented_text: str,
    *,
    out_path: str | Path | None = None,
    backup: bool = False,
    atomic: bool = True,
) -> dict[str, str | None]:
    current_file = Path(current_path)
    current_loaded = load_text_file(current_file)

    target_file = Path(out_path) if out_path is not None else current_file
    outputs: dict[str, str | None] = {
        "out_path": str(target_file),
        "backup_path": None,
    }

    stat_meta = current_loaded.stat_meta
    if target_file.exists():
        target_loaded = load_text_file(target_file)
        stat_meta = target_loaded.stat_meta

    output_format_meta: TextFormatMeta = current_loaded.format_meta
    output_bytes = encode_text_for_write(augmented_text, meta=output_format_meta)

    if out_path is None and backup:
        backup_path = Path(str(current_file) + _timestamp_suffix())
        if backup_path.exists():
            raise FileExistsError(f"backup destination already exists: {backup_path}")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        backup_path.write_bytes(current_file.read_bytes())
        _apply_stat(backup_path, stat_meta=current_loaded.stat_meta)
        outputs["backup_path"] = str(backup_path)

    if atomic:
        _atomic_write(target_file, output_bytes, stat_meta=stat_meta)
    else:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(output_bytes)
        _apply_stat(target_file, stat_meta=stat_meta)

    return outputs


def augment_file(
    current_path: str | Path,
    extension_path: str | Path,
    *,
    out_path: str | Path | None = None,
    backup: bool = False,
    atomic: bool = True,
    check: bool = False,
    **augment_options: Any,
) -> Report:
    current_file = Path(current_path)
    extension_file = Path(extension_path)

    current_loaded = load_text_file(current_file)
    extension_loaded = load_text_file(extension_file)

    current_text = current_loaded.text
    extension_text = extension_loaded.text

    augmented_text, report = augment_text(current_text, extension_text, **augment_options)

    target_file = Path(out_path) if out_path is not None else current_file
    report.outputs["out_path"] = str(target_file)
    report.outputs["backup_path"] = None

    if check or not report.changed:
        return report

    report.outputs.update(
        write_augmented_text(
            current_file,
            augmented_text,
            out_path=out_path,
            backup=backup,
            atomic=atomic,
        )
    )

    return report
