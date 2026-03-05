from __future__ import annotations

import pytest

from yamlaug.pointer import format_json_pointer, parse_json_pointer, resolve_pointer


def test_pointer_roundtrip_with_escape() -> None:
    tokens = ["a/b", "x~y", 2]
    ptr = format_json_pointer(tokens)
    assert ptr == "/a~1b/x~0y/2"
    assert parse_json_pointer(ptr) == ["a/b", "x~y", "2"]


def test_pointer_must_start_with_slash() -> None:
    with pytest.raises(ValueError):
        parse_json_pointer("a/b")


def test_resolve_pointer_numeric_string_mapping_key() -> None:
    root = {"a": {"1": {"name": "mapping-key"}}}
    assert resolve_pointer(root, "/a/1/name") == "mapping-key"


def test_resolve_pointer_sequence_index() -> None:
    root = {"a": [{"name": "zero"}, {"name": "one"}]}
    assert resolve_pointer(root, "/a/1/name") == "one"


def test_resolve_pointer_ambiguous_same_str_different_key_types_raises() -> None:
    root = {"a": {1: "int-key", "1": "str-key"}}
    with pytest.raises(ValueError, match="ambiguous key token"):
        resolve_pointer(root, "/a/1")


def test_resolve_pointer_unique_bool_key_token_resolves() -> None:
    root = {"a": {True: "bool-key"}}
    assert resolve_pointer(root, "/a/True") == "bool-key"
