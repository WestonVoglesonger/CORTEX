# Telemetry – Metrics, Units, and File Formats

Defines what the harness records per window and how it is written to disk.
Use this spec to interpret CSV/JSON and build plots consistently.

## Files
- `results/<run_id>/telemetry.csv`
- `results/<run_id>/telemetry.json`
- Optional plots in `results/<run_id>/plots/`

## Common columns (per window)
| Column | Unit | Notes |
|---|---|---|
| run_id | — | Hash or label of the run |
| plugin | — | Kernel name (`car`, `notch_iir`, …) |
| dtype | — | `float32` \| `q15` \| `q7` |
| window_index | — | 0-based |
| release_ts_ns | ns | Monotonic clock |
| deadline_ts_ns | ns | Monotonic clock |
| start_ts_ns | ns | When `process()` called |
| end_ts_ns | ns | When output ready |
| deadline_missed | 0/1 | `end_ts_ns > deadline_ts_ns` |

## Derived timing metrics (per window)
| Metric | Unit | Definition |
|---|---|---|
| latency_ns | ns | `end_ts_ns - last_input_arrival_ts_ns` |
| jitter_p95_minus_p50 | ns | computed per run |
| jitter_p99_minus_p50 | ns | computed per run |
| throughput_windows_per_s | 1/s | computed per run |

> Notes: jitter summaries (p50, p95, p99) are reported per plugin per run.

## Memory metrics (per window or per run)
| Metric | Unit | Notes |
|---|---|---|
| rss_bytes | bytes | Process RSS (approx) |
| state_bytes | bytes | From plugin metadata |
| workspace_bytes | bytes | From plugin metadata |

## Energy/Power (per window)
| Metric | Unit | Definition |
|---|---|---|
| energy_j | J | RAPL delta around `process()` |
| power_mw | mW | `energy_j * (Fs / H) * 1000` |

## Shape/context columns
| Column | Unit | Notes |
|---|---|---|
| W | samples | Window length |
| H | samples | Hop length |
| C | channels | Input channels |
| Fs | Hz | Sample rate |
| load_profile | — | `idle` \| `medium` \| `heavy` |
| repeat | — | Repeat index |
| warmup | 0/1 | Excluded from stats if 1 |

## CSV rules
- Delimiter: `,`
- Header: yes
- Encoding: UTF-8

## JSON rules
- Array of objects with the same keys as CSV headers.

## Aggregates (per plugin per run)
- p50/p95/p99 of latency (ns)
- jitter: p95−p50, p99−p50 (ns)
- deadline_miss_rate (%)
- mean/median power (mW)
- summary table written to `results/<run_id>/summary.csv`

## Reproducibility notes
- Record git commit, build flags, CPU model, governor, turbo, and RT settings.
- Save run config snapshot to `results/<run_id>/cortex.yaml`.
