from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WarningRecord:
    code: str
    message: str
    current_path: str | None = None
    current_line: int | None = None
    extension_path: str | None = None
    extension_line: int | None = None
    current_pointer: str | None = None
    extension_pointer: str | None = None


@dataclass
class Report:
    changed: bool = False
    warnings: list[WarningRecord] = field(default_factory=list)
    statistics: dict[str, int] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)


@dataclass
class Options:
    under: str = ""
    under_norm: str = "/"
    fill_empty_path: str | None = None
    fill_empty_types: set[str] = field(default_factory=set)
    add_missing: bool = False
    warn_list_diff_len: bool = False
    warn_list_diff_exact: bool = False
    warn_current_only: bool = False
    warn_unattached_comment: bool = False
    warn_under: tuple[str, ...] = field(default_factory=tuple)
    warn_except: tuple[str, ...] = field(default_factory=tuple)
    quiet: bool = False
    warn_all: bool = False
    allow_expand_scalar_to_dict: bool = False
    expanded_scalar_refuge: str = "__yamlaug_expanded_scalar_values__"


def normalize_fill_empty_types(fill_empty_types: str | list[str] | tuple[str, ...] | set[str] | None) -> set[str]:
    if fill_empty_types is None:
        return set()

    if isinstance(fill_empty_types, str):
        tokens = [part.strip() for part in fill_empty_types.split(",") if part.strip()]
    else:
        tokens = [str(part).strip() for part in fill_empty_types if str(part).strip()]

    lowered = {token.lower() for token in tokens}
    if "all" in lowered:
        return {"null", "string", "list", "dict"}

    allowed = {"null", "string", "list", "dict"}
    unknown = lowered.difference(allowed)
    if unknown:
        raise ValueError(f"unknown fill_empty_types: {sorted(unknown)}")
    return lowered


def normalize_options(
    *,
    under: str = "",
    fill_empty_path: str | None = None,
    fill_empty_types: str | list[str] | tuple[str, ...] | set[str] | None = None,
    add_missing: bool = False,
    warn_list_diff_len: bool = False,
    warn_list_diff_exact: bool = False,
    warn_current_only: bool = False,
    warn_unattached_comment: bool = False,
    warn_under: list[str] | tuple[str, ...] | None = None,
    warn_except: list[str] | tuple[str, ...] | None = None,
    quiet: bool = False,
    warn_all: bool = False,
    allow_expand_scalar_to_dict: bool = False,
    expanded_scalar_refuge: str = "__yamlaug_expanded_scalar_values__",
) -> Options:
    if quiet and warn_all:
        raise ValueError("quiet and warn_all cannot both be true")

    normalized_warn_under = tuple(warn_under or ())
    normalized_warn_except = tuple(warn_except or ())

    for pointer in list(normalized_warn_under) + list(normalized_warn_except):
        if pointer and not pointer.startswith("/"):
            raise ValueError(f"warning pointer must start with '/': {pointer}")

    if under and not under.startswith("/"):
        raise ValueError("under must start with '/'")

    under_norm = "/" if under in ("", "/") else under.rstrip("/")

    if fill_empty_path is not None and not fill_empty_path.startswith("/"):
        raise ValueError("fill_empty_path must start with '/'")

    return Options(
        under=under,
        under_norm=under_norm,
        fill_empty_path=fill_empty_path,
        fill_empty_types=normalize_fill_empty_types(fill_empty_types),
        add_missing=add_missing,
        warn_list_diff_len=warn_list_diff_len,
        warn_list_diff_exact=warn_list_diff_exact,
        warn_current_only=warn_current_only,
        warn_unattached_comment=warn_unattached_comment,
        warn_under=normalized_warn_under,
        warn_except=normalized_warn_except,
        quiet=quiet,
        warn_all=warn_all,
        allow_expand_scalar_to_dict=allow_expand_scalar_to_dict,
        expanded_scalar_refuge=expanded_scalar_refuge,
    )
