from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .io import load_yaml_rt
from .pointer import child_pointer


def extract_preceding_comments(yaml_text: str, *, source_name: str = "<memory>") -> tuple[dict[str, list[str]], list[str]]:
    """Extract preceding comments for YAML keys and return them by JSON Pointer.

    This function parses YAML in ruamel round-trip mode and collects comment tokens
    from comment association fields (for example, mapping-level leading comments,
    key-level comment bundles, and mapping end comments). Because ruamel can attach
    a comment to the previous key or mapping, this function reassigns each comment
    block to the next key that appears later in the document.

    The primary return value is a dictionary where each key is a JSON Pointer path
    (for example, "/device/receiver") and each value is a list of comment lines
    that describe that key immediately before it appears.

    Empty comment lines are preserved as empty strings in the output list.

    Any comment block that does not have a following key target is returned in the
    secondary list as unattached trailing comments.

    Args:
        yaml_text: Full YAML text to parse.
        source_name: Source label forwarded to YAML loader metadata. Useful for
            diagnostics when parser errors are raised.

    Returns:
        A tuple of:
        - comments_by_path: Mapping from JSON Pointer path to list of comment lines.
        - trailing: List of unattached trailing comment lines.

    Notes:
        - Paths follow JSON Pointer style used in this project.
        - Comment markers are stripped from each returned line.
        - Newline styles are normalized to LF for line splitting.
        - Non-comment token text, if present, is preserved as stripped text.
    """
    root, _ = load_yaml_rt(yaml_text, source_name=source_name)
    if root is None:
        return {}, []

    targets: list[_Target] = []
    blocks: list[_CommentBlock] = []
    _collect_targets_and_blocks(root, pointer="/", targets=targets, blocks=blocks)

    targets.sort(key=lambda item: (item.line, item.order))
    blocks.sort(key=lambda item: (item.line, item.order))

    comments_by_path: dict[str, list[str]] = {}
    trailing: list[str] = []
    target_index = 0
    for block in blocks:
        while target_index < len(targets) and targets[target_index].line <= block.line:
            target_index += 1
        if target_index >= len(targets):
            trailing.extend(block.lines)
            continue
        _append_lines(comments_by_path, targets[target_index].path, block.lines)

    return comments_by_path, trailing


@dataclass
class _Target:
    path: str
    line: int
    order: int


@dataclass
class _CommentBlock:
    line: int
    order: int
    lines: list[str]


def _collect_targets_and_blocks(
    node: Any,
    *,
    pointer: str,
    targets: list[_Target],
    blocks: list[_CommentBlock],
) -> None:
    if isinstance(node, CommentedMap):
        _collect_mapping_targets(node, pointer=pointer, targets=targets)
        _collect_mapping_blocks(node, blocks=blocks)
        for key, value in node.items():
            child_ptr = child_pointer(pointer, key)
            _collect_targets_and_blocks(value, pointer=child_ptr, targets=targets, blocks=blocks)
        return

    if isinstance(node, Mapping):
        for key, value in node.items():
            child_ptr = child_pointer(pointer, key)
            _collect_targets_and_blocks(value, pointer=child_ptr, targets=targets, blocks=blocks)
        return

    if isinstance(node, CommentedSeq):
        for index, value in enumerate(node):
            child_ptr = child_pointer(pointer, index)
            _collect_targets_and_blocks(value, pointer=child_ptr, targets=targets, blocks=blocks)
        return

    if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
        for index, value in enumerate(node):
            child_ptr = child_pointer(pointer, index)
            _collect_targets_and_blocks(value, pointer=child_ptr, targets=targets, blocks=blocks)


def _collect_mapping_targets(mapping: CommentedMap, *, pointer: str, targets: list[_Target]) -> None:
    line_col = getattr(mapping, "lc", None)
    if line_col is None:
        return

    for key in mapping.keys():
        line = _mapping_key_line(line_col, key)
        if line is None:
            continue
        targets.append(_Target(path=child_pointer(pointer, key), line=line, order=len(targets)))


def _collect_mapping_blocks(mapping: CommentedMap, *, blocks: list[_CommentBlock]) -> None:
    comment_assoc = getattr(mapping, "ca", None)
    if comment_assoc is None:
        return

    leading_tokens = _coerce_token_list(getattr(comment_assoc, "comment", None), prefer_second=True)
    _append_tokens_as_blocks(blocks, leading_tokens)

    items = getattr(comment_assoc, "items", None)
    if isinstance(items, dict):
        keys = list(mapping.keys())
        for key in keys:
            bundle = items.get(key)
            if not isinstance(bundle, (list, tuple)) or len(bundle) < 3:
                continue
            _append_tokens_as_blocks(blocks, [bundle[2]])

    end_tokens = _coerce_token_list(getattr(comment_assoc, "end", None), prefer_second=False)
    _append_tokens_as_blocks(blocks, end_tokens)


def _append_tokens_as_blocks(blocks: list[_CommentBlock], tokens: list[Any]) -> None:
    for token in tokens:
        line = _token_line(token)
        lines = _token_to_lines(token)
        if line is None or not lines:
            continue
        blocks.append(_CommentBlock(line=line, order=len(blocks), lines=lines))


def _mapping_key_line(line_col: Any, key: Any) -> int | None:
    key_func = getattr(line_col, "key", None)
    if not callable(key_func):
        return None

    value = key_func(key)
    if isinstance(value, tuple) and value and isinstance(value[0], int):
        return value[0] + 1
    if isinstance(value, int):
        return value + 1
    return None


def _token_line(token: Any) -> int | None:
    marker = getattr(token, "start_mark", None)
    line = getattr(marker, "line", None)
    if isinstance(line, int):
        return line + 1
    return None


def _append_lines(store: dict[str, list[str]], path: str, lines: list[str]) -> None:
    if not lines:
        return
    if path not in store:
        store[path] = []
    store[path].extend(lines)


def _coerce_token_list(raw: Any, *, prefer_second: bool) -> list[Any]:
    if raw is None:
        return []

    if isinstance(raw, list) and prefer_second and len(raw) >= 2 and isinstance(raw[1], list):
        return raw[1]

    if isinstance(raw, list):
        return raw

    if isinstance(raw, tuple):
        return list(raw)

    return [raw]


def _tokens_to_lines(tokens: list[Any]) -> list[str]:
    result: list[str] = []
    for token in tokens:
        result.extend(_token_to_lines(token))
    return result


def _token_to_lines(token: Any) -> list[str]:
    value = getattr(token, "value", None)
    if not isinstance(value, str):
        return []

    normalized = value.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.split("\n")
    if lines and lines[-1] == "":
        lines = lines[:-1]
    if lines and lines[0] == "":
        # ruamel comment token values often begin with a structural newline.
        # Dropping one leading empty keeps explicit blank lines while avoiding
        # an inconsistent extra empty item in the extracted output.
        lines = lines[1:]

    result: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "":
            result.append("")
            continue

        marker = line.find("#")
        if marker >= 0:
            text = line[marker + 1:].lstrip()
            result.append(text)
            continue

        result.append(stripped)
    return result
