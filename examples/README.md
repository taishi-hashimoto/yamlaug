# Examples

## Example 1. Migration from v1 to v1.1, while keeping the user's modification:

```bash
yamlaug examples/radar_config_v1.yaml  --by examples/radar_config_v1_1.yaml -n -k extension --allow-overwrite --overwrite-path /version --overwrite-path /profile_name
```

## Example 2. 

```bash
yamlaug examples/radar_config_v1.yaml --by examples/radar_config_v2.yaml -n -k extension --allow-overwrite --overwrite-path /version --overwrite-path /profile_name -m /device/receiver:/hardware/receiver/model -m /device/serial:/hardware/receiver/serial -m /device/clock_source:/hardware/receiver/clock/source -m /radar/center_frequency_hz:/rf/center_frequency_hz -m /radar/tx_power_dbm:/rf/tx/power_dbm -m /radar/mode:/waveform/type -m /waveform/chirp_duration_ms:/waveform/chirp/duration_ms -m /waveform/sweep_bandwidth_hz:/waveform/chirp/sweep_bandwidth_hz -m /receiver/sample_rate_sps:/acquisition/sample_rate_sps
```