from __future__ import annotations

from pathlib import Path

import pytest

from yamlaug.comment import extract_preceding_comments


def _read_example(name: str) -> str:
    return Path("examples", name).read_text(encoding="utf-8")


def test_extract_preceding_comments_v1_key_mapping_and_trailing() -> None:
    text = _read_example("radar_config_v1.yaml")

    comments, trailing = extract_preceding_comments(text, source_name="examples/radar_config_v1.yaml")

    assert comments["/version"][0] == "SDR radar control configuration file (Version 1.0)"
    assert "Configuration profile name" in comments["/profile_name"]
    assert "Device connection settings" in comments["/device"]
    assert comments["/device/receiver"] == ["Receiver device name"]
    assert "Radar operation settings" in comments["/radar"]
    assert "" in comments["/device"]

    assert "Some notes: this configuration is intentionally conservative and focused on stability and compatibility with existing post-processing scripts. " in trailing
    assert "Future versions will explore more aggressive settings for improved performance once the core system is verified to be stable." in trailing
    assert "" in trailing


@pytest.mark.parametrize(
    "example_name, expected_paths",
    [
        ("radar_config_v1.yaml", ["/version", "/device", "/device/receiver", "/dsp/cfar/threshold_db"]),
        ("radar_config_v1_1.yaml", ["/version", "/radar/calibration", "/receiver/agc/target_rssi_dbfs", "/output/iq_path"]),
        ("radar_config_v2.yaml", ["/schema", "/hardware/channels/0/role", "/processing/detection/guard_cells", "/telemetry/destination"]),
    ],
)
def test_extract_preceding_comments_examples_smoke(example_name: str, expected_paths: list[str]) -> None:
    text = _read_example(example_name)

    comments, trailing = extract_preceding_comments(text, source_name=f"examples/{example_name}")

    assert comments
    assert all(path.startswith("/") for path in comments)
    for path in expected_paths:
        assert path in comments
        assert isinstance(comments[path], list)
        assert all(isinstance(line, str) for line in comments[path])

    assert isinstance(trailing, list)
    assert all(isinstance(line, str) for line in trailing)
