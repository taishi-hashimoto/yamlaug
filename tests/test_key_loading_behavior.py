from __future__ import annotations

from typing import Any

import pytest
import yaml
from ruamel.yaml import YAML
from ruamel.yaml.constructor import DuplicateKeyError


KEY_DOUBLE_QUOTED_HOGE = """\
hoge: 1
\"hoge\": 2
"""

KEY_SINGLE_QUOTED_HOGE = """\
hoge: 1
'hoge': 2
"""

KEYS_INT_AND_STRING_NUMERIC = """\
1: one
\"1\": two
"""


def _load_with_pyyaml(text: str) -> Any:
    return yaml.safe_load(text)


def _load_with_ruamel(text: str) -> Any:
    parser = YAML(typ="rt")
    return parser.load(text)


def test_key_double_quoted_hoge_loader_behavior() -> None:
    text = KEY_DOUBLE_QUOTED_HOGE

    py_data = _load_with_pyyaml(text)
    assert isinstance(py_data, dict)
    assert py_data == {"hoge": 2}

    with pytest.raises(DuplicateKeyError):
        _load_with_ruamel(text)


def test_key_single_quoted_hoge_loader_behavior() -> None:
    text = KEY_SINGLE_QUOTED_HOGE

    py_data = _load_with_pyyaml(text)
    assert isinstance(py_data, dict)
    assert py_data == {"hoge": 2}

    with pytest.raises(DuplicateKeyError):
        _load_with_ruamel(text)


def test_keys_int_and_string_numeric_loader_behavior() -> None:
    text = KEYS_INT_AND_STRING_NUMERIC

    py_data = _load_with_pyyaml(text)
    ruamel_data = _load_with_ruamel(text)

    assert isinstance(py_data, dict)
    assert py_data == {1: "one", "1": "two"}

    assert isinstance(ruamel_data, dict)
    assert ruamel_data == {1: "one", "1": "two"}
