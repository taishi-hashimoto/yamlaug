from __future__ import annotations

from .pointer import pointer_is_under
from .types import Options, Report, WarningRecord


DEFAULT_ENABLED_CODES = {"YAG101", "YAG103", "YAG301"}
_UNSET = object()
ALL_CODES = {
    "YAG001",
    "YAG101",
    "YAG102",
    "YAG103",
    "YAG104",
    "YAG201",
    "YAG301",
    "YAG401",
}


def should_emit_warning(code: str, pointer: str, options: Options) -> bool:
    if options.quiet:
        return False
    if options.warn_all:
        base_enabled = True
    else:
        if code == "YAG201":
            base_enabled = options.warn_current_only
        elif code == "YAG401":
            base_enabled = options.warn_unattached_comment
        else:
            base_enabled = code in DEFAULT_ENABLED_CODES

    if not base_enabled:
        return False

    if options.warn_under:
        if not any(pointer_is_under(pointer, include_pointer) for include_pointer in options.warn_under):
            return False

    for exclude_pointer in options.warn_except:
        if pointer_is_under(pointer, exclude_pointer):
            return False

    return True


def make_warning(
    *,
    code: str,
    message: str,
    pointer: str,
    current_line: int | None = None,
    extension_line: int | None = None,
    current_pointer: str | None | object = _UNSET,
    extension_pointer: str | None | object = _UNSET,
    current_path: str | None | object = _UNSET,
    extension_path: str | None | object = _UNSET,
) -> WarningRecord:
    resolved_current_pointer = pointer if current_pointer is _UNSET else current_pointer
    resolved_extension_pointer = pointer if extension_pointer is _UNSET else extension_pointer
    resolved_current_path = resolved_current_pointer if current_path is _UNSET else current_path
    resolved_extension_path = resolved_extension_pointer if extension_path is _UNSET else extension_path

    return WarningRecord(
        code=code,
        message=message,
        current_path=resolved_current_path,
        current_line=current_line,
        extension_path=resolved_extension_path,
        extension_line=extension_line,
        current_pointer=resolved_current_pointer,
        extension_pointer=resolved_extension_pointer,
    )


def add_warning(report: Report, warning: WarningRecord) -> None:
    report.warnings.append(warning)
