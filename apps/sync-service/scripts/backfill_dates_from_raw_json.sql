-- One-off backfill: populate start_date, target_date, created_date,
-- activated_date, and closed_date on work_items directly from the
-- fields already stored in raw_json, without re-syncing from Azure DevOps.
--
-- Safe to run multiple times (idempotent — just overwrites with the same
-- values). Not required for new syncs: the app already extracts these
-- columns going forward. This is only for rows synced before that change.
--
-- ADO date fields look like "2026-01-10T00:00:00Z" or
-- "2026-01-10T00:00:00.617Z" (variable-precision fractional seconds).
-- The (\.\d+)?Z$ pattern strips the optional fraction and the trailing
-- "Z", matching how the app parses these same fields in Python.

UPDATE work_items
SET
    start_date = regexp_replace(
        raw_json -> 'fields' ->> 'Microsoft.VSTS.Scheduling.StartDate',
        '(\.\d+)?Z$', ''
    )::timestamp,
    target_date = regexp_replace(
        raw_json -> 'fields' ->> 'Microsoft.VSTS.Scheduling.TargetDate',
        '(\.\d+)?Z$', ''
    )::timestamp,
    created_date = regexp_replace(
        raw_json -> 'fields' ->> 'System.CreatedDate',
        '(\.\d+)?Z$', ''
    )::timestamp,
    activated_date = regexp_replace(
        raw_json -> 'fields' ->> 'Microsoft.VSTS.Common.ActivatedDate',
        '(\.\d+)?Z$', ''
    )::timestamp,
    closed_date = regexp_replace(
        raw_json -> 'fields' ->> 'Microsoft.VSTS.Common.ClosedDate',
        '(\.\d+)?Z$', ''
    )::timestamp
WHERE raw_json IS NOT NULL;
