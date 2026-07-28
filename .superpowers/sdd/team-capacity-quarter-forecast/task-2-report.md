# Task 2 report — capacity snapshot and forecast

## Status

Implemented the pure `build_capacity_snapshot` aggregation in
`apps/sync-service/app/capacity.py`. The snapshot is JSON-safe and includes
the required generated timestamp, history start, twelve calendar-month
throughput buckets, type-specific and aggregate forecasts, flow metrics,
warnings, and reliability fields.

Throughput counts only the last zero-duration final-state interval per work
item, so reopened work is counted only at its final completion. Forecasts use
non-zero delivery months per work-item type, with nearest-rank P25/P50/P75
multiplied by three and floored. Flow metrics expose per-status median seconds
and the mapped upstream, downstream, and development-cycle totals.

## TDD evidence

The initial focused forecast test failed during collection because
`build_capacity_snapshot` did not yet exist. After the minimal implementation,
the test passed and the complete focused suite passed.

## Commit

`b31db0c feat: calculate capacity forecast snapshots`

## Tests

```powershell
& 'C:\Projects\AzureSync\apps\sync-service\.venv\Scripts\python.exe' -m pytest tests/test_capacity.py -v
```

Output: `11 passed in 0.10s`.

The focused coverage includes percentile forecasting for `[2, 4, 6]`, exactly
twelve zero-filled months, insufficient delivery history, independent type
forecasts, and reopening with a later final transition.

## Concerns

The task worktree has pre-existing untracked coordination artifacts under
`.superpowers/sdd/team-capacity-quarter-forecast/`; they were intentionally not
included in the implementation commit.

## Fix round 1

Filtered final completion candidates to `ended_at <= as_of` before selecting
the last completion for each work item. This preserves an in-window final
transition when a later final transition exists in the future. Added the
corresponding regression test and parameterized the `Technical Analysis`
downstream mapping test across Feature, Technical Feature, Incident, and
Problem.

Command:

```powershell
& 'C:\Projects\AzureSync\apps\sync-service\.venv\Scripts\python.exe' -m pytest tests/test_capacity.py -v
```

Output: `15 passed in 0.13s`.
