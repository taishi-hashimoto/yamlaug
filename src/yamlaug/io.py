from __future__ import annotations

import codecs
from dataclasses import dataclass
from io import StringIO
from pathlib import Path
import re
from typing import Any

import chardet
from ruamel.yaml import YAML


@dataclass
class YamlMeta:
    source_name: str


@dataclass
class TextFormatMeta:
    encoding: str
    newline: str | None
    bom: bytes


@dataclass
class FileStatMeta:
    mode: int
    uid: int
    gid: int


@dataclass
class LoadedTextFile:
    text: str
    format_meta: TextFormatMeta
    stat_meta: FileStatMeta


_BOM_CANDIDATES: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF8, "utf-8"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


_yaml_loader = YAML(typ="rt")
_yaml_loader.preserve_quotes = True

_yaml_dumper = YAML(typ="rt")
_yaml_dumper.preserve_quotes = True
_yaml_dumper.default_flow_style = False

_ENCODING_CONFIDENCE_THRESHOLD = 0.2


def _detect_bom(raw: bytes) -> tuple[bytes, str | None]:
    for bom, encoding in _BOM_CANDIDATES:
        if raw.startswith(bom):
            return bom, encoding
    return b"", None


def _detect_encoding(raw: bytes) -> str:
    result = chardet.detect(raw)
    encoding = result.get("encoding")
    confidence = result.get("confidence")

    if not encoding:
        raise ValueError("failed to detect file encoding")
    if confidence is None or confidence < _ENCODING_CONFIDENCE_THRESHOLD:
        raise ValueError(f"encoding confidence too low: {encoding} ({confidence})")

    return str(encoding)


def _normalize_encoding_name(encoding: str) -> str:
    return codecs.lookup(encoding).name


def _detect_newline(text: str) -> str | None:
    newline_match = re.search(r"\r\n|\n|\r", text)
    if newline_match is None:
        return None
    return newline_match.group(0)


def normalize_newline(text: str, newline: str | None) -> str:
    if newline is None:
        return text
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    if newline == "\n":
        return normalized
    return normalized.replace("\n", newline)


def load_text_file(path: str | Path) -> LoadedTextFile:
    file_path = Path(path)
    raw = file_path.read_bytes()

    bom, bom_encoding = _detect_bom(raw)
    encoding = bom_encoding or _detect_encoding(raw)
    normalized_encoding = _normalize_encoding_name(encoding)
    decode_encoding = "utf-8-sig" if bom == codecs.BOM_UTF8 else normalized_encoding

    try:
        text = raw.decode(decode_encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(f"failed to decode file with detected encoding {normalized_encoding}: {file_path}") from exc

    stat = file_path.stat()
    return LoadedTextFile(
        text=text,
        format_meta=TextFormatMeta(
            encoding=normalized_encoding,
            newline=_detect_newline(text),
            bom=bom,
        ),
        stat_meta=FileStatMeta(
            mode=stat.st_mode & 0o777,
            uid=stat.st_uid,
            gid=stat.st_gid,
        ),
    )


def encode_text_for_write(text: str, *, meta: TextFormatMeta) -> bytes:
    text_with_newline = normalize_newline(text, meta.newline)
    encoded = text_with_newline.encode(meta.encoding)
    if meta.bom and not encoded.startswith(meta.bom):
        return meta.bom + encoded
    return encoded


def load_yaml_rt(text: str, *, source_name: str) -> tuple[Any, YamlMeta]:
    data = _yaml_loader.load(text)
    return data, YamlMeta(source_name=source_name)


def dump_yaml_rt(node: Any) -> str:
    stream = StringIO()
    _yaml_dumper.dump(node, stream)
    return stream.getvalue()


def get_line(node: Any) -> int | None:
    line_info = getattr(node, "lc", None)
    if line_info is None:
        return None

    line_value = getattr(line_info, "line", None)
    if line_value is not None:
        return int(line_value) + 1

    if isinstance(line_info, tuple) and line_info:
        maybe_line = line_info[0]
        if isinstance(maybe_line, int):
            return maybe_line + 1

    return None
