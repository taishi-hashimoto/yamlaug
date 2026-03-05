from __future__ import annotations

import copy
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ruamel.yaml.comments import CommentedMap, CommentedSeq

from .io import dump_yaml_rt, get_line, load_yaml_rt
from .pointer import (
    child_pointer,
    format_json_pointer,
    parse_json_pointer,
    pointer_is_under,
    resolve_mapping_key,
    resolve_pointer,
)
from .types import Options, Report, normalize_options
from .warnings import add_warning, make_warning, should_emit_warning


def _report_with_defaults() -> Report:
    return Report(
        changed=False,
        warnings=[],
        statistics={
            "added_keys": 0,
            "filled": 0,
            "skipped_subtrees": 0,
            "list_items_added": 0,
            "type_mismatches": 0,
            "expanded_scalars": 0,
            "unattached_comments": 0,
        },
        outputs={},
    )


def _has_anchor_name(node: Any) -> bool:
    anchor = getattr(node, "anchor", None)
    return anchor is not None and bool(getattr(anchor, "value", None))


def _build_anchor_reference_index(root: Any, *, start_pointer: str = "/") -> tuple[dict[int, int], dict[int, str]]:
    counts: dict[int, int] = {}
    first_pointers: dict[int, str] = {}
    expanded: set[int] = set()

    def walk(node: Any, pointer: str) -> None:
        if _has_anchor_name(node):
            node_id = id(node)
            counts[node_id] = counts.get(node_id, 0) + 1
            if node_id not in first_pointers:
                first_pointers[node_id] = pointer

        if not isinstance(node, (Mapping, list, tuple, CommentedSeq, CommentedMap)):
            return

        node_id = id(node)
        if node_id in expanded:
            return
        expanded.add(node_id)

        if isinstance(node, Mapping):
            for key, value in node.items():
                walk(value, child_pointer(pointer, key))
        else:
            for index, value in enumerate(node):
                walk(value, child_pointer(pointer, index))

    walk(root, start_pointer)
    return counts, first_pointers


def _resolve_parent_and_key(root: Any, pointer: str) -> tuple[Any, Any]:
    if pointer in ("", "/"):
        raise ValueError("root pointer has no parent")

    tokens = parse_json_pointer(pointer)
    if not tokens:
        raise ValueError("root pointer has no parent")

    parent_tokens = tokens[:-1]
    parent_pointer = format_json_pointer(parent_tokens)
    parent = resolve_pointer(root, parent_pointer)
    key_token = tokens[-1]

    if isinstance(parent, (list, tuple, CommentedSeq)):
        try:
            index = int(key_token)
        except ValueError as exc:
            raise ValueError(f"under pointer token is not a list index: {key_token}") from exc
        if index < 0:
            raise ValueError("negative index is not allowed")
        return parent, index

    if not isinstance(parent, Mapping):
        raise ValueError(f"under pointer parent is not mapping/sequence: {pointer}")
    return parent, resolve_mapping_key(parent, key_token)


def _is_alias_reference_node(
    node: Any,
    pointer: str,
    anchor_counts: dict[int, int],
    anchor_first_pointers: dict[int, str],
) -> bool:
    if not _has_anchor_name(node):
        return False

    node_id = id(node)
    if anchor_counts.get(node_id, 0) <= 1:
        return False

    return anchor_first_pointers.get(node_id) != pointer


def _is_detached_comment_like(comment_token: Any) -> bool:
    text = getattr(comment_token, "value", "")
    if not isinstance(text, str):
        return False
    return re.search(r"\n\s*\n\s*#", text) is not None


def _collect_unattached_comment_hits(node: Any, pointer: str = "/") -> list[tuple[str, Any, str]]:
    hits: list[tuple[str, Any, str]] = []

    comment_assoc = getattr(node, "ca", None)
    if comment_assoc is not None:
        end_comments = getattr(comment_assoc, "end", None)
        if isinstance(end_comments, list):
            for token in end_comments:
                if token is not None and _is_detached_comment_like(token):
                    hits.append((pointer, token, "end"))

        items = getattr(comment_assoc, "items", None)
        if isinstance(items, dict):
            for item_key, bundle in items.items():
                if not isinstance(bundle, list):
                    continue
                for slot_index, token in enumerate(bundle):
                    if isinstance(token, list):
                        for nested in token:
                            if nested is not None and _is_detached_comment_like(nested):
                                hits.append((child_pointer(pointer, item_key), nested, f"item[{slot_index}]"))
                    elif token is not None and _is_detached_comment_like(token):
                        hits.append((child_pointer(pointer, item_key), token, f"item[{slot_index}]"))

    if isinstance(node, Mapping):
        for key, value in node.items():
            hits.extend(_collect_unattached_comment_hits(value, child_pointer(pointer, key)))
    elif isinstance(node, (list, tuple, CommentedSeq)):
        for idx, value in enumerate(node):
            hits.extend(_collect_unattached_comment_hits(value, child_pointer(pointer, idx)))

    dedup: list[tuple[str, Any, str]] = []
    seen: set[tuple[str, int | None, str]] = set()
    for hit_pointer, token, origin in hits:
        start = getattr(token, "start_mark", None)
        line_number = int(start.line) if start is not None and hasattr(start, "line") else None
        key = (hit_pointer, line_number, origin)
        if key in seen:
            continue
        seen.add(key)
        dedup.append((hit_pointer, token, origin))
    return dedup


def _emit_unattached_comment_warnings(
    root: Any,
    *,
    source_name: str,
    start_pointer: str,
    options: Options,
    report: Report,
) -> None:
    for pointer, token, origin in _collect_unattached_comment_hits(root, start_pointer):
        report.statistics["unattached_comments"] += 1
        line = getattr(token, "start_mark", None)
        line_number = None
        if line is not None and hasattr(line, "line"):
            line_number = int(line.line) + 1

        if should_emit_warning("YAG401", pointer, options):
            add_warning(
                report,
                make_warning(
                    code="YAG401",
                    message=f"unattached comment token found in {source_name} ({origin})",
                    pointer=pointer,
                    current_line=line_number if source_name == "current" else None,
                    extension_line=line_number if source_name == "extension" else None,
                    current_pointer=pointer if source_name == "current" else None,
                    extension_pointer=pointer if source_name == "extension" else None,
                    current_path=pointer if source_name == "current" else None,
                    extension_path=pointer if source_name == "extension" else None,
                ),
            )


def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (Mapping, list, tuple, CommentedSeq, CommentedMap))


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return len(value) > 0
    if isinstance(value, (list, tuple, CommentedSeq, Mapping, CommentedMap)):
        return len(value) > 0
    return True


def _is_empty_value(value: Any, empty_types: set[str]) -> bool:
    if "null" in empty_types and value is None:
        return True
    if "string" in empty_types and isinstance(value, str) and len(value) == 0:
        return True
    if "list" in empty_types and isinstance(value, (list, tuple, CommentedSeq)) and len(value) == 0:
        return True
    if "dict" in empty_types and isinstance(value, (Mapping, CommentedMap)) and len(value) == 0:
        return True
    return False


def _detect_special_token_kind(node: Any) -> str | None:
    if isinstance(node, Mapping):
        if "<<" in node:
            return "mergekey"
        merge_value = getattr(node, "merge", None)
        if merge_value:
            return "mergekey"

    if _has_anchor_name(node):
        return "anchor"

    return None


def _emit_warning_if_enabled(
    *,
    report: Report,
    options: Options,
    code: str,
    pointer: str,
    message: str,
    current_node: Any = None,
    extension_node: Any = None,
) -> None:
    if not should_emit_warning(code, pointer or "/", options):
        return

    add_warning(
        report,
        make_warning(
            code=code,
            message=message,
            pointer=pointer or "/",
            current_line=get_line(current_node),
            extension_line=get_line(extension_node),
        ),
    )


def _find_matching_key(current_map: Mapping[Any, Any], extension_key: Any) -> tuple[Any | None, bool]:
    if extension_key in current_map:
        return extension_key, False

    candidates = [existing_key for existing_key in current_map.keys() if str(existing_key) == str(extension_key)]
    if len(candidates) == 1:
        return candidates[0], type(candidates[0]) is not type(extension_key)

    return None, False


def _emit_yag104_for_mapping_collisions(
    *,
    mapping: Mapping[Any, Any],
    pointer: str,
    options: Options,
    report: Report,
    source: str,
) -> None:
    grouped: dict[str, list[Any]] = {}
    for key in mapping.keys():
        grouped.setdefault(str(key), []).append(key)

    for normalized, keys in grouped.items():
        distinct_types = {type(key) for key in keys}
        if len(keys) <= 1 or len(distinct_types) <= 1:
            continue

        type_names = ", ".join(sorted({tp.__name__ for tp in distinct_types}))
        message = f"key type ambiguity for normalized key '{normalized}' in {source}: {type_names}"
        if source == "current":
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG104",
                pointer=pointer,
                message=message,
                current_node=mapping,
                extension_node=None,
            )
        else:
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG104",
                pointer=pointer,
                message=message,
                current_node=None,
                extension_node=mapping,
            )


def _clone_comment_for_new_key(extension_map: Mapping[Any, Any], key: Any) -> Any:
    comment_assoc = getattr(extension_map, "ca", None)
    if comment_assoc is None:
        return None

    items = getattr(comment_assoc, "items", None)
    if not isinstance(items, dict):
        return None

    key_comment = items.get(key)
    if key_comment is None:
        return None

    return copy.deepcopy(key_comment)


def _clone_leading_comment_attached_to_previous_key(extension_map: Mapping[Any, Any], key: Any) -> Any:
    keys = list(extension_map.keys())
    try:
        index = keys.index(key)
    except ValueError:
        return None

    if index == 0:
        return None

    prev_key = keys[index - 1]
    comment_assoc = getattr(extension_map, "ca", None)
    if comment_assoc is None:
        return None

    items = getattr(comment_assoc, "items", None)
    if not isinstance(items, dict):
        return None

    prev_comment = items.get(prev_key)
    if not prev_comment or len(prev_comment) < 3:
        return None

    return copy.deepcopy(prev_comment[2])


def _attach_comment_to_new_key(current_map: Mapping[Any, Any], key: Any, comment_bundle: Any) -> None:
    if comment_bundle is None:
        return

    comment_assoc = getattr(current_map, "ca", None)
    if comment_assoc is None:
        return

    items = getattr(comment_assoc, "items", None)
    if not isinstance(items, dict):
        return

    items[key] = comment_bundle


def _attach_leading_comment_to_previous_current_key(
    current_map: Mapping[Any, Any],
    previous_key: Any,
    leading_comment: Any,
) -> None:
    if leading_comment is None:
        return

    comment_assoc = getattr(current_map, "ca", None)
    if comment_assoc is None:
        return

    items = getattr(comment_assoc, "items", None)
    if not isinstance(items, dict):
        return

    existing = items.get(previous_key)
    if existing is None:
        existing = [None, None, None, None]
    else:
        existing = list(existing) + [None] * max(0, 4 - len(existing))

    if existing[2] is None:
        existing[2] = copy.deepcopy(leading_comment)
        items[previous_key] = existing


def _move_scalar_to_refuge(root_map: Mapping[Any, Any], pointer: str, scalar_value: Any, refuge_key: str) -> None:
    if refuge_key not in root_map:
        root_map[refuge_key] = CommentedMap()

    target = root_map[refuge_key]
    if not isinstance(target, Mapping):
        raise ValueError(f"refuge key is not a mapping: {refuge_key}")
    tokens = parse_json_pointer(pointer)

    for idx, token in enumerate(tokens):
        if idx == len(tokens) - 1:
            if token not in target:
                target[token] = copy.deepcopy(scalar_value)
        else:
            if token not in target:
                target[token] = CommentedMap()
            elif not isinstance(target[token], Mapping):
                return
            target = target[token]


def _move_overwritten_value_to_refuge(root_map: Mapping[Any, Any], pointer: str, value: Any, refuge_key: str) -> None:
    if refuge_key not in root_map:
        root_map[refuge_key] = CommentedMap()

    refuge_root = root_map[refuge_key]
    if not isinstance(refuge_root, Mapping):
        raise ValueError(f"overwrite refuge key is not a mapping: {refuge_key}")

    tokens = parse_json_pointer(pointer)
    if not tokens:
        if "__root__" not in refuge_root:
            refuge_root["__root__"] = copy.deepcopy(value)
        return

    target = refuge_root
    for idx, token in enumerate(tokens):
        if idx == len(tokens) - 1:
            if token not in target:
                target[token] = copy.deepcopy(value)
        else:
            if token not in target:
                target[token] = CommentedMap()
            elif not isinstance(target[token], Mapping):
                return
            target = target[token]


def _augment_sequence(
    current_seq: Sequence[Any],
    extension_seq: Sequence[Any],
    *,
    pointer: str,
    options: Options,
    report: Report,
    root_current: Any,
    current_anchor_counts: dict[int, int],
    current_anchor_first_pointers: dict[int, str],
    extension_anchor_counts: dict[int, int],
    extension_anchor_first_pointers: dict[int, str],
) -> bool:
    changed = False

    for index, current_item in enumerate(current_seq):
        item_pointer = child_pointer(pointer, index)
        if _is_alias_reference_node(current_item, item_pointer, current_anchor_counts, current_anchor_first_pointers):
            report.statistics["skipped_subtrees"] += 1
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG301",
                pointer=item_pointer,
                message=f"special token detected (alias); subtree root {pointer} skipped",
                current_node=current_item,
                extension_node=None,
            )
            return False

    for index, extension_item in enumerate(extension_seq):
        item_pointer = child_pointer(pointer, index)
        if _is_alias_reference_node(extension_item, item_pointer, extension_anchor_counts, extension_anchor_first_pointers):
            report.statistics["skipped_subtrees"] += 1
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG301",
                pointer=item_pointer,
                message=f"special token detected (alias); subtree root {pointer} skipped",
                current_node=None,
                extension_node=extension_item,
            )
            return False

    if options.warn_list_diff_len and len(current_seq) != len(extension_seq):
        _emit_warning_if_enabled(
            report=report,
            options=options,
            code="YAG101",
            pointer=pointer,
            message="list length differs; current is kept",
            current_node=current_seq,
            extension_node=extension_seq,
        )

    if options.warn_list_diff_exact and current_seq != extension_seq:
        _emit_warning_if_enabled(
            report=report,
            options=options,
            code="YAG101",
            pointer=pointer,
            message="list contents differ; current is kept",
            current_node=current_seq,
            extension_node=extension_seq,
        )

    if options.add_missing:
        current_scalar_only = all(_is_scalar(item) for item in current_seq)
        extension_scalar_only = all(_is_scalar(item) for item in extension_seq)
        if current_scalar_only and extension_scalar_only and isinstance(current_seq, (list, CommentedSeq)):
            for ext_item in extension_seq:
                if ext_item not in current_seq:
                    current_seq.append(copy.deepcopy(ext_item))
                    report.statistics["list_items_added"] += 1
                    changed = True

    return changed


def _augment_mapping(
    current_map: Mapping[Any, Any],
    extension_map: Mapping[Any, Any],
    *,
    pointer: str,
    options: Options,
    report: Report,
    root_current: Any,
    current_anchor_counts: dict[int, int],
    current_anchor_first_pointers: dict[int, str],
    extension_anchor_counts: dict[int, int],
    extension_anchor_first_pointers: dict[int, str],
) -> bool:
    changed = False
    extension_keys = list(extension_map.keys())

    _emit_yag104_for_mapping_collisions(
        mapping=current_map,
        pointer=pointer,
        options=options,
        report=report,
        source="current",
    )
    _emit_yag104_for_mapping_collisions(
        mapping=extension_map,
        pointer=pointer,
        options=options,
        report=report,
        source="extension",
    )

    for current_key, current_value in current_map.items():
        child_ptr = child_pointer(pointer, current_key)
        if _is_alias_reference_node(current_value, child_ptr, current_anchor_counts, current_anchor_first_pointers):
            report.statistics["skipped_subtrees"] += 1
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG301",
                pointer=child_ptr,
                message=f"special token detected (alias); subtree root {pointer} skipped",
                current_node=current_value,
                extension_node=None,
            )
            return False

    for extension_key, extension_value in extension_map.items():
        child_ptr = child_pointer(pointer, extension_key)
        if _is_alias_reference_node(extension_value, child_ptr, extension_anchor_counts, extension_anchor_first_pointers):
            report.statistics["skipped_subtrees"] += 1
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG301",
                pointer=child_ptr,
                message=f"special token detected (alias); subtree root {pointer} skipped",
                current_node=None,
                extension_node=extension_value,
            )
            return False

    extension_matched_keys: set[Any] = set()
    for index, extension_key in enumerate(extension_keys):
        extension_value = extension_map[extension_key]
        child_ptr = child_pointer(pointer, extension_key)
        matched_key, _ = _find_matching_key(current_map, extension_key)

        if matched_key is None:
            if options.skip_missing_keys:
                continue
            if isinstance(current_map, (dict, CommentedMap)):
                current_map[extension_key] = copy.deepcopy(extension_value)
                _attach_comment_to_new_key(
                    current_map,
                    extension_key,
                    _clone_comment_for_new_key(extension_map, extension_key),
                )
                if index > 0:
                    previous_extension_key = extension_keys[index - 1]
                    previous_current_key, _ = _find_matching_key(current_map, previous_extension_key)
                    if previous_current_key is not None:
                        _attach_leading_comment_to_previous_current_key(
                            current_map,
                            previous_current_key,
                            _clone_leading_comment_attached_to_previous_key(extension_map, extension_key),
                        )
                report.statistics["added_keys"] += 1
                changed = True
                _emit_warning_if_enabled(
                    report=report,
                    options=options,
                    code="YAG001",
                    pointer=child_ptr,
                    message="extension-only key added",
                    current_node=None,
                    extension_node=extension_value,
                )
            continue

        extension_matched_keys.add(matched_key)

        child_changed = _augment_node(
            current=current_map[matched_key],
            extension=extension_value,
            pointer=child_ptr,
            options=options,
            report=report,
            root_current=root_current,
            parent=current_map,
            key_in_parent=matched_key,
            current_anchor_counts=current_anchor_counts,
            current_anchor_first_pointers=current_anchor_first_pointers,
            extension_anchor_counts=extension_anchor_counts,
            extension_anchor_first_pointers=extension_anchor_first_pointers,
        )
        changed = changed or child_changed

    if options.order_by == "extension" and isinstance(current_map, (dict, CommentedMap)):
        target_keys: list[Any] = []
        for extension_key in extension_keys:
            matched_key, _ = _find_matching_key(current_map, extension_key)
            if matched_key is None:
                continue
            if matched_key not in target_keys:
                target_keys.append(matched_key)

        for current_key in list(current_map.keys()):
            if current_key not in target_keys:
                target_keys.append(current_key)

        if hasattr(current_map, "move_to_end"):
            for key in target_keys:
                current_map.move_to_end(key)
        else:
            for key in target_keys:
                value = current_map.pop(key)
                current_map[key] = value

    if options.warn_current_only:
        for current_key in current_map.keys():
            if current_key not in extension_matched_keys and all(str(current_key) != str(ext_key) for ext_key in extension_map.keys()):
                child_ptr = child_pointer(pointer, current_key)
                _emit_warning_if_enabled(
                    report=report,
                    options=options,
                    code="YAG201",
                    pointer=child_ptr,
                    message="current-only key kept",
                    current_node=current_map.get(current_key),
                    extension_node=None,
                )

    return changed


def _maybe_apply_fill_empty(
    *,
    current: Any,
    extension: Any,
    pointer: str,
    options: Options,
    report: Report,
    parent: Any,
    key_in_parent: Any,
) -> bool:
    if options.fill_empty_path:
        should_fill = pointer == options.fill_empty_path
    else:
        should_fill = _is_empty_value(current, options.fill_empty_types)

    if not should_fill:
        return False

    if not _is_non_empty(extension):
        return False

    if parent is None:
        return False

    parent[key_in_parent] = copy.deepcopy(extension)
    report.statistics["filled"] += 1

    _emit_warning_if_enabled(
        report=report,
        options=options,
        code="YAG102",
        pointer=pointer,
        message="fill-empty applied",
        current_node=current,
        extension_node=extension,
    )
    return True


def _is_overwrite_target(pointer: str, options: Options) -> bool:
    if not options.allow_overwrite or not options.overwrite_paths:
        return False
    return any(pointer_is_under(pointer, overwrite_path) for overwrite_path in options.overwrite_paths)


def _replace_root_in_place(current: Any, replacement: Any) -> bool:
    if isinstance(current, (dict, CommentedMap)) and isinstance(replacement, Mapping):
        current.clear()
        for key, value in replacement.items():
            current[key] = copy.deepcopy(value)
        return True

    if isinstance(current, (list, CommentedSeq)) and isinstance(replacement, (list, tuple, CommentedSeq)):
        current.clear()
        for item in replacement:
            current.append(copy.deepcopy(item))
        return True

    return False


def _maybe_apply_overwrite(
    *,
    current: Any,
    extension: Any,
    pointer: str,
    options: Options,
    report: Report,
    root_current: Any,
    parent: Any,
    key_in_parent: Any,
) -> bool:
    if not _is_overwrite_target(pointer, options):
        return False

    if type(current) is not type(extension) and not options.allow_overwrite_different_type:
        _emit_warning_if_enabled(
            report=report,
            options=options,
            code="YAG106",
            pointer=pointer,
            message="overwrite skipped due to type mismatch",
            current_node=current,
            extension_node=extension,
        )
        return False

    if pointer != "/":
        if not isinstance(root_current, Mapping):
            raise ValueError("overwrite refuge requires mapping root")
        _move_overwritten_value_to_refuge(root_current, pointer, current, options.overwrite_refuge)

    if parent is None:
        previous_root = copy.deepcopy(current)
        if not _replace_root_in_place(current, extension):
            if type(current) is not type(extension):
                raise ValueError(
                    "cannot overwrite root with different type; use a non-root --overwrite-path"
                )
            raise ValueError("cannot overwrite root in-place for this YAML root type")
        if not isinstance(current, Mapping):
            raise ValueError("overwrite refuge requires mapping root")
        _move_overwritten_value_to_refuge(current, pointer, previous_root, options.overwrite_refuge)
    else:
        parent[key_in_parent] = copy.deepcopy(extension)

    warning_code = "YAG107" if type(current) is not type(extension) else "YAG105"
    _emit_warning_if_enabled(
        report=report,
        options=options,
        code=warning_code,
        pointer=pointer,
        message="node overwritten by extension",
        current_node=current,
        extension_node=extension,
    )
    return True


def _augment_node(
    *,
    current: Any,
    extension: Any,
    pointer: str,
    options: Options,
    report: Report,
    root_current: Any,
    parent: Any,
    key_in_parent: Any,
    current_anchor_counts: dict[int, int],
    current_anchor_first_pointers: dict[int, str],
    extension_anchor_counts: dict[int, int],
    extension_anchor_first_pointers: dict[int, str],
) -> bool:
    special_current = _detect_special_token_kind(current)
    if _is_alias_reference_node(current, pointer, current_anchor_counts, current_anchor_first_pointers):
        special_current = "alias"

    special_extension = _detect_special_token_kind(extension)
    if _is_alias_reference_node(extension, pointer, extension_anchor_counts, extension_anchor_first_pointers):
        special_extension = "alias"
    if special_current or special_extension:
        report.statistics["skipped_subtrees"] += 1
        kind = special_current or special_extension
        _emit_warning_if_enabled(
            report=report,
            options=options,
            code="YAG301",
            pointer=pointer,
            message=f"special token detected ({kind}); subtree skipped",
            current_node=current,
            extension_node=extension,
        )
        return False

    if _maybe_apply_overwrite(
        current=current,
        extension=extension,
        pointer=pointer,
        options=options,
        report=report,
        root_current=root_current,
        parent=parent,
        key_in_parent=key_in_parent,
    ):
        return True

    if _maybe_apply_fill_empty(
        current=current,
        extension=extension,
        pointer=pointer,
        options=options,
        report=report,
        parent=parent,
        key_in_parent=key_in_parent,
    ):
        return True

    if isinstance(current, Mapping) and isinstance(extension, Mapping):
        return _augment_mapping(
            current,
            extension,
            pointer=pointer,
            options=options,
            report=report,
            root_current=root_current,
            current_anchor_counts=current_anchor_counts,
            current_anchor_first_pointers=current_anchor_first_pointers,
            extension_anchor_counts=extension_anchor_counts,
            extension_anchor_first_pointers=extension_anchor_first_pointers,
        )

    if isinstance(current, (list, tuple, CommentedSeq)) and isinstance(extension, (list, tuple, CommentedSeq)):
        return _augment_sequence(
            current,
            extension,
            pointer=pointer,
            options=options,
            report=report,
            root_current=root_current,
            current_anchor_counts=current_anchor_counts,
            current_anchor_first_pointers=current_anchor_first_pointers,
            extension_anchor_counts=extension_anchor_counts,
            extension_anchor_first_pointers=extension_anchor_first_pointers,
        )

    if type(current) is not type(extension):
        report.statistics["type_mismatches"] += 1
        if (
            options.allow_expand_scalar_to_dict
            and _is_scalar(current)
            and isinstance(extension, Mapping)
            and len(extension) > 0
            and parent is not None
            and isinstance(root_current, Mapping)
        ):
            _move_scalar_to_refuge(root_current, pointer, current, options.expanded_scalar_refuge)
            parent[key_in_parent] = copy.deepcopy(extension)
            report.statistics["expanded_scalars"] += 1
            _emit_warning_if_enabled(
                report=report,
                options=options,
                code="YAG103",
                pointer=pointer,
                message="scalar expanded to dict (overwritten)",
                current_node=current,
                extension_node=extension,
            )
            return True

        _emit_warning_if_enabled(
            report=report,
            options=options,
            code="YAG101",
            pointer=pointer,
            message="type mismatch kept current",
            current_node=current,
            extension_node=extension,
        )

    return False


def to_plain_data(node: Any) -> Any:
    if isinstance(node, Mapping):
        return {key: to_plain_data(value) for key, value in node.items()}
    if isinstance(node, (list, tuple, CommentedSeq)):
        return [to_plain_data(item) for item in node]
    return node


def augment_text(
    current_text: str,
    extension_text: str,
    *,
    under: str = "",
    fill_empty_path: str | None = None,
    fill_empty_types: str | list[str] | tuple[str, ...] | set[str] | None = None,
    add_missing: bool = False,
    skip_missing_keys: bool = False,
    warn_list_diff_len: bool = False,
    warn_list_diff_exact: bool = False,
    warn_current_only: bool = False,
    warn_unattached_comment: bool = False,
    warn_under: list[str] | tuple[str, ...] | None = None,
    warn_except: list[str] | tuple[str, ...] | None = None,
    quiet: bool = False,
    warn_all: bool = False,
    order_by: str = "current",
    allow_expand_scalar_to_dict: bool = False,
    expanded_scalar_refuge: str = "__yamlaug_expanded_scalar_values__",
    allow_overwrite: bool = False,
    overwrite_path: str | list[str] | tuple[str, ...] | set[str] | None = None,
    overwrite_refuge: str = "__yamlaug_overwritten_values__",
    allow_overwrite_different_type: bool = False,
) -> tuple[str, Report]:
    options = normalize_options(
        under=under,
        fill_empty_path=fill_empty_path,
        fill_empty_types=fill_empty_types,
        add_missing=add_missing,
        skip_missing_keys=skip_missing_keys,
        warn_list_diff_len=warn_list_diff_len,
        warn_list_diff_exact=warn_list_diff_exact,
        warn_current_only=warn_current_only,
        warn_unattached_comment=warn_unattached_comment,
        warn_under=warn_under,
        warn_except=warn_except,
        quiet=quiet,
        warn_all=warn_all,
        order_by=order_by,
        allow_expand_scalar_to_dict=allow_expand_scalar_to_dict,
        expanded_scalar_refuge=expanded_scalar_refuge,
        allow_overwrite=allow_overwrite,
        overwrite_path=overwrite_path,
        overwrite_refuge=overwrite_refuge,
        allow_overwrite_different_type=allow_overwrite_different_type,
    )

    report = _report_with_defaults()

    current_root, _ = load_yaml_rt(current_text, source_name="current")
    extension_root, _ = load_yaml_rt(extension_text, source_name="extension")

    if options.under_norm == "/":
        current_sub = current_root
        extension_sub = extension_root
        merge_parent = None
        merge_key = None
    else:
        current_sub = resolve_pointer(current_root, options.under_norm)
        extension_sub = resolve_pointer(extension_root, options.under_norm)
        merge_parent, merge_key = _resolve_parent_and_key(current_root, options.under_norm)

    if options.fill_empty_path:
        if not pointer_is_under(options.fill_empty_path, options.under_norm):
            raise ValueError("fill_empty_path must be under under")
        resolve_pointer(current_root, options.fill_empty_path)

    if options.allow_overwrite and options.overwrite_paths:
        for overwrite_path in options.overwrite_paths:
            if not pointer_is_under(overwrite_path, options.under_norm):
                raise ValueError("overwrite_path must be under under")

    _emit_unattached_comment_warnings(
        current_sub,
        source_name="current",
        start_pointer=options.under_norm,
        options=options,
        report=report,
    )
    _emit_unattached_comment_warnings(
        extension_sub,
        source_name="extension",
        start_pointer=options.under_norm,
        options=options,
        report=report,
    )

    current_anchor_counts, current_anchor_first_pointers = _build_anchor_reference_index(
        current_sub,
        start_pointer=options.under_norm,
    )
    extension_anchor_counts, extension_anchor_first_pointers = _build_anchor_reference_index(
        extension_sub,
        start_pointer=options.under_norm,
    )

    before_plain = to_plain_data(current_root)

    _augment_node(
        current=current_sub,
        extension=extension_sub,
        pointer=options.under_norm,
        options=options,
        report=report,
        root_current=current_root,
        parent=merge_parent,
        key_in_parent=merge_key,
        current_anchor_counts=current_anchor_counts,
        current_anchor_first_pointers=current_anchor_first_pointers,
        extension_anchor_counts=extension_anchor_counts,
        extension_anchor_first_pointers=extension_anchor_first_pointers,
    )

    after_plain = to_plain_data(current_root)
    report.changed = before_plain != after_plain

    return dump_yaml_rt(current_root), report
