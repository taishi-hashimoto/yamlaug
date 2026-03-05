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
    skip_missing_keys: bool = False
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
    order_by: str = "current"
    allow_overwrite: bool = False
    overwrite_paths: tuple[str, ...] | None = None
    overwrite_refuge: str = "__yamlaug_overwritten_values__"
    allow_overwrite_different_type: bool = False


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
    skip_missing_keys: bool = False,
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
    order_by: str = "current",
    allow_overwrite: bool = False,
    overwrite_path: str | list[str] | tuple[str, ...] | set[str] | None = None,
    overwrite_refuge: str = "__yamlaug_overwritten_values__",
    allow_overwrite_different_type: bool = False,
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

    if order_by not in {"current", "extension"}:
        raise ValueError("order_by must be one of: current, extension")

    if not overwrite_refuge:
        raise ValueError("overwrite_refuge must not be empty")

    normalized_overwrite_paths: tuple[str, ...] | None = None
    if overwrite_path is not None:
        if isinstance(overwrite_path, str):
            raw_paths = [overwrite_path]
        else:
            raw_paths = [str(path) for path in overwrite_path]

        normalized_list: list[str] = []
        for raw_path in raw_paths:
            if raw_path in ("", "/"):
                normalized_path = "/"
            else:
                if not raw_path.startswith("/"):
                    raise ValueError(f"overwrite_path must start with '/': {raw_path}")
                normalized_path = raw_path.rstrip("/")

            if normalized_path not in normalized_list:
                normalized_list.append(normalized_path)

        normalized_overwrite_paths = tuple(normalized_list)

    if allow_overwrite and not normalized_overwrite_paths:
        raise ValueError("--allow-overwrite requires at least one --overwrite-path")

    if not allow_overwrite and normalized_overwrite_paths:
        raise ValueError("--overwrite-path requires --allow-overwrite")

    return Options(
        under=under,
        under_norm=under_norm,
        fill_empty_path=fill_empty_path,
        fill_empty_types=normalize_fill_empty_types(fill_empty_types),
        add_missing=add_missing,
        skip_missing_keys=skip_missing_keys,
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
        order_by=order_by,
        allow_overwrite=allow_overwrite,
        overwrite_paths=normalized_overwrite_paths,
        overwrite_refuge=overwrite_refuge,
        allow_overwrite_different_type=allow_overwrite_different_type,
    )
