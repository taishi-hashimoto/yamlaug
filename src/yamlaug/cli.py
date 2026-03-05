"yamlaug CLI"

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from .core import augment_text
from .file_api import augment_file
from .io import load_text_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="yamlaug")
    parser.add_argument("current")
    parser.add_argument("--by", required=True, dest="extension")
    parser.add_argument("--under", default="")
    parser.add_argument("-n", "--dry-run", action="store_true")
    parser.add_argument("--color", choices=["auto", "always", "never"], default="auto")
    parser.add_argument("-o", "--out")
    parser.add_argument("-c", "--check", action="store_true")
    parser.add_argument("-q", "--quiet", action="store_true")
    parser.add_argument("-w", "--warn-all", action="store_true")
    parser.add_argument("--warn-current-only", action="store_true")
    parser.add_argument("--warn-unattached-comment", action="store_true")
    parser.add_argument("--warn-under", action="append", default=[])
    parser.add_argument("--warn-except", action="append", default=[])
    parser.add_argument("--add-missing", action="store_true")
    parser.add_argument("--warn-list-diff-len", action="store_true")
    parser.add_argument("--warn-list-diff-exact", action="store_true")
    parser.add_argument("--fill-empty-path")
    parser.add_argument("--fill-empty-types")
    parser.add_argument("--allow-expand-scalar-to-dict", action="store_true")
    parser.add_argument("--expanded-scalar-refuge", default="__yamlaug_expanded_scalar_values__")
    parser.add_argument("--no-backup", action="store_true")
    return parser


def _print_warnings(report) -> None:
    for item in report.warnings:
        pointer = item.current_pointer or item.extension_pointer or "/"
        line = item.current_line or item.extension_line
        if line is None:
            print(f"{item.code}: {item.message} ({pointer})", file=sys.stderr)
        else:
            print(f"{item.code}: {item.message} ({pointer}, line {line})", file=sys.stderr)


def _print_dry_run_yaml(text: str, *, color_mode: str = "auto") -> None:
    if color_mode == "never":
        print(text, end="")
        return

    is_tty = sys.stdout.isatty()
    if color_mode == "auto" and not is_tty:
        print(text, end="")
        return

    try:
        from rich.console import Console
        from rich.syntax import Syntax
    except Exception:
        print(text, end="")
        return

    force_terminal = color_mode == "always" or (color_mode == "auto" and is_tty)
    console = Console(force_terminal=force_terminal)
    console.print(Syntax(text, "yaml", line_numbers=False, word_wrap=False), end="")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    augment_options = dict(
        under=args.under,
        fill_empty_path=args.fill_empty_path,
        fill_empty_types=args.fill_empty_types,
        add_missing=args.add_missing,
        warn_list_diff_len=args.warn_list_diff_len,
        warn_list_diff_exact=args.warn_list_diff_exact,
        warn_current_only=args.warn_current_only,
        warn_unattached_comment=args.warn_unattached_comment,
        warn_under=args.warn_under,
        warn_except=args.warn_except,
        quiet=args.quiet,
        warn_all=args.warn_all,
        allow_expand_scalar_to_dict=args.allow_expand_scalar_to_dict,
        expanded_scalar_refuge=args.expanded_scalar_refuge,
    )

    try:
        if args.check:
            report = augment_file(
                args.current,
                args.extension,
                out_path=args.out,
                backup=not args.no_backup,
                check=True,
                **augment_options,
            )
            _print_warnings(report)
            return 1 if report.changed else 0

        if args.dry_run:
            current_text = load_text_file(Path(args.current)).text
            extension_text = load_text_file(Path(args.extension)).text

            augmented_text, report = augment_text(current_text, extension_text, **augment_options)
            _print_dry_run_yaml(augmented_text, color_mode=args.color)
            _print_warnings(report)
            return 0

        report = augment_file(
            args.current,
            args.extension,
            out_path=args.out,
            backup=not args.no_backup,
            check=False,
            **augment_options,
        )
        _print_warnings(report)
        return 0
    except Exception as exc:
        print(f"yamlaug error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
