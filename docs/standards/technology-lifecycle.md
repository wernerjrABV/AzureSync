# Technology Lifecycle Standard

## Semestral stack review

Every officially adopted technology (see the corporate stack list below)
must be reviewed every 6 months for: continued fit, known vulnerabilities,
support status, and whether a newer major version should be adopted.

Cadence: January and July of each year. Record the review outcome as a
dated entry appended to this file (or a linked ADR if the review results in
a change).

## Annual upgrade rule: V-2

For any technology with major versions, this repository targets the
"current major version minus 2" (V-2) at most, reviewed annually. Example:
if the latest major is V10, this repo should be on V8 or newer within one
year of V10's release. Falling further behind than V-2 requires an ADR
explaining why (e.g. a breaking change not yet absorbed) and a remediation
date.

## Corporate stack baseline (as of 2026-07-15)

- Backend: Java 23+, C# 10+, Python 3.12+
- Frontend: React 19+, Angular 21+
- Mobile: Android 11+, iOS 22+, Flutter 3.27+
- Database: PostgreSQL 16+, MongoDB 7+, SQL Server 2022+
- Test: Cypress, WebdriverIO, k6, Apache JMeter, Appium
- Hot Sites: Acquia, Wix
- Cloud/Observability/Tracking: Azure, Datadog, FullStory, Smartlook, Hotjar
- Code Quality/Security: GitHub, SonarQube, Snyk, Apiiro
- Boards: Azure DevOps

## Applying this to the current repo

- `apps/sync-service` runs Python — track it against the Python 3.12+
  baseline and this repo's own `requirements.txt` pins.
- The database is PostgreSQL — track it against the PostgreSQL 16+
  baseline.
- Future `apps/api-read` and `apps/web-read` must pick their stack from the
  baseline above at scaffold time (see their own design specs).

## Review log

| Date | Reviewer | Outcome |
|---|---|---|
| 2026-07-15 | (initial) | Standard established; no prior review to compare against. |
