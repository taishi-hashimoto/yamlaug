from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class PointerResolutionError(ValueError):
    pass


def resolve_mapping_key(mapping: Mapping[Any, Any], token: str) -> Any:
    candidates = [key for key in mapping.keys() if str(key) == token]
    if not candidates:
        raise PointerResolutionError(f"key not found: {token}")

    distinct_types = {type(key) for key in candidates}
    if len(candidates) > 1 and len(distinct_types) > 1:
        raise PointerResolutionError(
            f"ambiguous key token: {token} (multiple keys with same str() and different types)"
        )

    return candidates[0]


def _decode_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _encode_token(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def parse_json_pointer(ptr: str) -> list[str]:
    if ptr in ("", "/"):
        return []
    if not ptr.startswith("/"):
        raise ValueError("JSON Pointer must start with '/'")

    raw_tokens = ptr.split("/")[1:]
    result: list[str] = []
    for token in raw_tokens:
        decoded = _decode_token(token)
        result.append(decoded)
    return result


def format_json_pointer(tokens: list[str | int]) -> str:
    if not tokens:
        return "/"
    encoded = [_encode_token(str(token)) for token in tokens]
    return "/" + "/".join(encoded)


def child_pointer(pointer: str, token: Any) -> str:
    encoded = _encode_token(str(token))
    if pointer in ("", "/"):
        return "/" + encoded
    return pointer + "/" + encoded


def resolve_pointer(root: Any, ptr: str) -> Any:
    tokens = parse_json_pointer(ptr)
    node = root
    for token in tokens:
        if isinstance(node, Sequence) and not isinstance(node, (str, bytes, bytearray)):
            try:
                index = int(token)
            except ValueError as exc:
                raise PointerResolutionError(f"not a valid sequence index: {token}") from exc
            if index < 0:
                raise PointerResolutionError("negative index is not allowed")
            if index >= len(node):
                raise PointerResolutionError(f"index out of range: {index}")
            node = node[index]
        else:
            if not isinstance(node, Mapping):
                raise PointerResolutionError(f"not a mapping at token {token}")
            resolved_key = resolve_mapping_key(node, token)
            node = node[resolved_key]
    return node


def pointer_is_under(pointer: str, root_pointer: str) -> bool:
    if root_pointer in ("", "/"):
        return True
    if pointer == root_pointer:
        return True
    return pointer.startswith(root_pointer.rstrip("/") + "/")
