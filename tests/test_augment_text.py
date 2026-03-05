from __future__ import annotations

from yamlaug import augment_text


def test_mapping_merge_add_and_keep_current() -> None:
    current = """
a: 1
b:
  c: 1
""".strip()
    extension = """
a: 9
b:
  c: 2
  d: 3
e: 4
""".strip()

    text, report = augment_text(current, extension)

    assert "a: 1" in text
    assert "d: 3" in text
    assert "e: 4" in text
    assert report.changed is True


def test_type_mismatch_keeps_current_and_warns_default() -> None:
    current = "a: 1\n"
    extension = "a:\n  x: 1\n"

    _, report = augment_text(current, extension)

    codes = [warning.code for warning in report.warnings]
    assert "YAG101" in codes


def test_fill_empty_applies() -> None:
    current = "a: ''\n"
    extension = "a: hello\n"

    text, report = augment_text(current, extension, fill_empty_types=["string"], warn_all=True)

    assert "hello" in text
    assert report.statistics["filled"] == 1
    assert any(warning.code == "YAG102" for warning in report.warnings)


def test_add_missing_on_scalar_list() -> None:
    current = "a: [1, 2]\n"
    extension = "a: [2, 3, 4]\n"

    text, report = augment_text(current, extension, add_missing=True)

    assert "- 3" in text or "[1, 2, 3, 4]" in text
    assert report.statistics["list_items_added"] == 2


def test_idempotence_data_model() -> None:
    current = "a: 1\n"
    extension = "a: 1\nb: 2\n"

    first_text, _ = augment_text(current, extension)
    second_text, second_report = augment_text(first_text, extension)

    assert first_text == second_text
    assert second_report.changed is False


def test_expand_scalar_to_dict() -> None:
    current = "root:\n  a: 1\n"
    extension = "root:\n  a:\n    nested: true\n"

    text, report = augment_text(current, extension, allow_expand_scalar_to_dict=True)

    assert "nested: true" in text
    assert "__yamlaug_expanded_scalar_values__" in text
    assert report.statistics["expanded_scalars"] == 1


def test_new_key_comment_is_transferred_best_effort() -> None:
    current = """
root:
    keep: 1
""".strip()
    extension = """
root:
    keep: 1
    # description for added
    added: 10 # eol for added
""".strip()

    text, _ = augment_text(current, extension)

    assert "description for added" in text
    assert "eol for added" in text
    assert "added: 10" in text


def test_existing_comments_in_current_are_preserved() -> None:
    current = """
# header comment
root:
    # keep description
    keep: 1 # keep eol
""".strip()
    extension = """
root:
    keep: 9
    extra: 2
""".strip()

    text, _ = augment_text(current, extension)

    assert "header comment" in text
    assert "keep description" in text
    assert "keep eol" in text


def test_unattached_comment_warning_opt_in() -> None:
    current = """
root:
    a: 1

    # detached block

    b: 2
""".strip()
    extension = "root:\n  a: 1\n  b: 2\n"

    _, report = augment_text(current, extension, warn_unattached_comment=True)

    codes = [warning.code for warning in report.warnings]
    assert "YAG401" in codes
    assert report.statistics["unattached_comments"] >= 1


def test_unattached_comment_warning_on_warn_all() -> None:
    current = """
a: 1

# detached top

b: 2
""".strip()
    extension = "a: 1\nb: 2\n"

    _, report = augment_text(current, extension, warn_all=True)

    assert any(warning.code == "YAG401" for warning in report.warnings)


def test_attached_comment_does_not_trigger_yag401() -> None:
    current = """
root:
    # attached description
    a: 1
""".strip()
    extension = "root:\n  a: 1\n"

    _, report = augment_text(current, extension, warn_unattached_comment=True)

    assert all(warning.code != "YAG401" for warning in report.warnings)


def test_yag401_has_current_side_fields_only_for_current_source() -> None:
    current = """
a: 1

# detached current

b: 2
""".strip()
    extension = "a: 1\nb: 2\n"

    _, report = augment_text(current, extension, warn_unattached_comment=True)

    warning = next(item for item in report.warnings if item.code == "YAG401")
    assert warning.current_pointer is not None
    assert warning.current_path is not None
    assert warning.extension_pointer is None
    assert warning.extension_path is None


def test_yag401_has_extension_side_fields_only_for_extension_source() -> None:
    current = "a: 1\nb: 2\n"
    extension = """
a: 1

# detached extension

b: 2
""".strip()

    _, report = augment_text(current, extension, warn_unattached_comment=True)

    warning = next(item for item in report.warnings if item.code == "YAG401")
    assert warning.extension_pointer is not None
    assert warning.extension_path is not None
    assert warning.current_pointer is None
    assert warning.current_path is None


def test_alias_in_mapping_value_skips_that_mapping_subtree() -> None:
    current = """
defaults: &def
    x: 1

service:
    conf: *def
""".strip()
    extension = """
defaults: &def
    x: 1
    y: 2

service:
    conf: *def
    added: true
""".strip()

    text, report = augment_text(current, extension)

    assert "added: true" not in text
    assert any(warning.code == "YAG301" for warning in report.warnings)
    alias_warnings = [
        warning
        for warning in report.warnings
        if warning.code == "YAG301" and "alias" in warning.message
    ]
    assert any(
        warning.current_pointer == "/service/conf" or warning.extension_pointer == "/service/conf"
        for warning in alias_warnings
    )
    assert any(
        warning.current_line is not None or warning.extension_line is not None
        for warning in alias_warnings
    )


def test_alias_in_sequence_skips_that_sequence_subtree() -> None:
    current = """
defaults: &def
    x: 1

arr:
    - *def
""".strip()
    extension = """
defaults: &def
    x: 1

arr:
    - *def
    - extra
""".strip()

    text, report = augment_text(current, extension, add_missing=True)

    assert "- extra" not in text
    assert any(warning.code == "YAG301" for warning in report.warnings)


def test_merge_key_mapping_skips_that_mapping_subtree() -> None:
        current = """
base: &base
    x: 1

service:
    <<: *base
    z: 9
""".strip()
        extension = """
base: &base
    x: 1
    y: 2

service:
    <<: *base
    z: 9
    added: true
""".strip()

        text, report = augment_text(current, extension)

        assert "added: true" not in text
        merge_warnings = [
                warning
                for warning in report.warnings
                if warning.code == "YAG301" and "mergekey" in warning.message
        ]
        assert merge_warnings
        assert any(
                warning.current_pointer == "/service" or warning.extension_pointer == "/service"
                for warning in merge_warnings
        )
        assert any(
                warning.current_line is not None or warning.extension_line is not None
                for warning in merge_warnings
        )


def test_anchor_mapping_skips_that_mapping_subtree() -> None:
        current = """
service: &svc
    host: localhost
""".strip()
        extension = """
service: &svc
    host: localhost
    port: 8080
""".strip()

        text, report = augment_text(current, extension)

        assert "port: 8080" not in text
        anchor_warnings = [
                warning
                for warning in report.warnings
                if warning.code == "YAG301" and "anchor" in warning.message
        ]
        assert anchor_warnings
        assert any(
                warning.current_pointer == "/service" or warning.extension_pointer == "/service"
                for warning in anchor_warnings
        )
        assert any(
                warning.current_line is not None or warning.extension_line is not None
                for warning in anchor_warnings
        )


def test_under_limits_changes_to_subtree() -> None:
    current = """
a:
  keep: 1
b:
  keep: 1
""".strip()
    extension = """
a:
  keep: 1
  add: yes
b:
  keep: 1
  add: yes
""".strip()

    text, _ = augment_text(current, extension, under="/a")

    assert "a:" in text
    assert "add: yes" in text
    assert "b:\n  keep: 1\n" in text


def test_allow_overwrite_replaces_only_targeted_path() -> None:
    current = "a: 1\nb: 1\n"
    extension = "a: 9\nb: 2\n"

    text, report = augment_text(current, extension, allow_overwrite=True, overwrite_path=["/a"])

    assert "a: 9" in text
    assert "b: 1" in text
    assert report.changed is True


def test_allow_overwrite_with_multiple_paths_is_or_condition() -> None:
    current = "a: 1\nb: 1\nc: 1\n"
    extension = "a: 9\nb: 8\nc: 7\n"

    text, report = augment_text(
        current,
        extension,
        allow_overwrite=True,
        overwrite_path=["/a", "/c"],
    )

    assert "a: 9" in text
    assert "b: 1" in text
    assert "c: 7" in text
    assert report.changed is True


def test_allow_overwrite_requires_overwrite_path() -> None:
    current = "a: 1\n"
    extension = "a: 9\n"

    try:
        augment_text(current, extension, allow_overwrite=True)
    except ValueError as exc:
        assert "--allow-overwrite requires at least one --overwrite-path" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_overwrite_path_requires_allow_overwrite() -> None:
    current = "a: 1\n"
    extension = "a: 9\n"

    try:
        augment_text(current, extension, overwrite_path=["/a"])
    except ValueError as exc:
        assert "--overwrite-path requires --allow-overwrite" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_overwrite_path_outside_under_errors() -> None:
    current = "a: 1\nb: 1\n"
    extension = "a: 9\nb: 9\n"

    try:
        augment_text(
            current,
            extension,
            under="/a",
            allow_overwrite=True,
            overwrite_path=["/b"],
        )
    except ValueError as exc:
        assert "overwrite_path must be under under" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_overwrite_type_mismatch_skipped_without_flag() -> None:
    current = "a: 1\n"
    extension = "a:\n  x: 1\n"

    text, report = augment_text(
        current,
        extension,
        allow_overwrite=True,
        overwrite_path=["/a"],
        warn_all=True,
    )

    assert "a: 1" in text
    assert any(warning.code == "YAG106" for warning in report.warnings)


def test_overwrite_type_mismatch_applies_with_flag() -> None:
    current = "a: 1\n"
    extension = "a:\n  x: 1\n"

    text, report = augment_text(
        current,
        extension,
        allow_overwrite=True,
        overwrite_path=["/a"],
        allow_overwrite_different_type=True,
        warn_all=True,
    )

    assert "x: 1" in text
    assert any(warning.code == "YAG107" for warning in report.warnings)


def test_allow_overwrite_moves_previous_value_to_default_overwrite_refuge() -> None:
    current = "a: 1\nb: 1\n"
    extension = "a: 9\nb: 2\n"

    text, _ = augment_text(
        current,
        extension,
        allow_overwrite=True,
        overwrite_path=["/a"],
    )

    assert "a: 9" in text
    assert "__yamlaug_overwritten_values__" in text
    assert "  a: 1" in text


def test_allow_overwrite_moves_previous_value_to_custom_overwrite_refuge() -> None:
    current = "a: 1\n"
    extension = "a: 9\n"

    text, _ = augment_text(
        current,
        extension,
        allow_overwrite=True,
        overwrite_path=["/a"],
        overwrite_refuge="__my_refuge__",
    )

    assert "__my_refuge__" in text
    assert "  a: 1" in text


def test_allow_overwrite_root_keeps_previous_root_under_refuge_root_slot() -> None:
    current = "a: 1\n"
    extension = "a: 9\n"

    text, _ = augment_text(
        current,
        extension,
        allow_overwrite=True,
        overwrite_path=["/"],
    )

    assert "a: 9" in text
    assert "__yamlaug_overwritten_values__" in text
    assert "__root__" in text


def test_overwrite_refuge_keeps_base_value_across_sequential_applies() -> None:
    base = "a: 1\n"
    ext1 = "a: 2\n"
    ext2 = "a: 3\n"

    text1, _ = augment_text(base, ext1, allow_overwrite=True, overwrite_path=["/a"])
    text2, _ = augment_text(text1, ext2, allow_overwrite=True, overwrite_path=["/a"])

    assert "a: 3" in text2
    assert "__yamlaug_overwritten_values__" in text2
    assert "  a: 1" in text2
    assert "  a: 2" not in text2


def test_expanded_scalar_refuge_accumulates_without_overwriting_existing_entry() -> None:
    base = "root:\n  a: 1\n  b: 2\n"
    ext1 = "root:\n  a:\n    x: 1\n  b: 2\n"
    ext2 = "root:\n  a:\n    x: 1\n  b:\n    y: 2\n"

    text1, _ = augment_text(base, ext1, allow_expand_scalar_to_dict=True)
    text2, _ = augment_text(text1, ext2, allow_expand_scalar_to_dict=True)

    assert "__yamlaug_expanded_scalar_values__" in text2
    assert "a: 1" in text2
    assert "b: 2" in text2


def test_order_by_current_keeps_existing_key_order() -> None:
    current = "b: 1\na: 1\nc: 1\n"
    extension = "a: 9\nb: 8\nd: 4\n"

    text, _ = augment_text(current, extension, order_by="current")

    lines = text.splitlines()
    b_index = lines.index("b: 1")
    a_index = lines.index("a: 1")
    c_index = lines.index("c: 1")
    d_index = lines.index("d: 4")
    assert b_index < a_index < c_index < d_index


def test_order_by_extension_uses_extension_order_then_current_only() -> None:
    current = "b: 1\na: 1\nc: 1\n"
    extension = "a: 9\nb: 8\nd: 4\n"

    text, _ = augment_text(current, extension, order_by="extension")

    lines = text.splitlines()
    a_index = lines.index("a: 1")
    b_index = lines.index("b: 1")
    d_index = lines.index("d: 4")
    c_index = lines.index("c: 1")
    assert a_index < b_index < d_index < c_index


def test_under_missing_in_current_errors() -> None:
    current = "a: 1\n"
    extension = "a: 1\n"

    try:
        augment_text(current, extension, under="/missing")
    except ValueError as exc:
        assert "key not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_under_missing_in_extension_errors() -> None:
    current = "a:\n  x: 1\n"
    extension = "a: {}\n"

    try:
        augment_text(current, extension, under="/a/x")
    except ValueError as exc:
        assert "key not found" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_fill_empty_path_outside_under_errors() -> None:
    current = "a: ''\nb: ''\n"
    extension = "a: hello\nb: world\n"

    try:
        augment_text(current, extension, under="/a", fill_empty_path="/b")
    except ValueError as exc:
        assert "fill_empty_path must be under under" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_quote_difference_does_not_trigger_yag104_double_quote() -> None:
    current = "hoge: 1\n"
    extension = '"hoge": 2\n'

    _, report = augment_text(current, extension, warn_all=True)

    assert all(warning.code != "YAG104" for warning in report.warnings)


def test_quote_difference_does_not_trigger_yag104_single_quote() -> None:
    current = "hoge: 1\n"
    extension = "'hoge': 2\n"

    _, report = augment_text(current, extension, warn_all=True)

    assert all(warning.code != "YAG104" for warning in report.warnings)


def test_int_and_string_numeric_keys_merge_to_existing_when_unique_by_str() -> None:
    current = "1: one\n"
    extension = '"1": two\n'

    text, report = augment_text(current, extension, warn_all=True)

    assert '"1": two' not in text
    assert report.changed is False


def test_yag104_emitted_when_str_equivalent_keys_with_different_types_coexist() -> None:
    current = '1: one\n"1": two\n'
    extension = '1: one\n"1": two\n'

    _, report = augment_text(current, extension, warn_all=True)

    assert any(warning.code == "YAG104" for warning in report.warnings)


def test_under_raises_on_ambiguous_numeric_pointer_token() -> None:
    current = '1: one\n"1": two\n'
    extension = '1: one\n"1": two\n'

    try:
        augment_text(current, extension, under="/1")
    except ValueError as exc:
        assert "ambiguous key token" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_under_raises_on_ambiguous_bool_string_pointer_token() -> None:
    current = 'true: yes\n"True": no\n'
    extension = 'true: yes\n"True": no\n'

    try:
        augment_text(current, extension, under="/True")
    except ValueError as exc:
        assert "ambiguous key token" in str(exc)
    else:
        raise AssertionError("expected ValueError")
