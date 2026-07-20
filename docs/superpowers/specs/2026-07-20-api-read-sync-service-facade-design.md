# API Read Sync-Service Facade Design

## Goal

Expose the full public area-path management API through `apps/api-read` while
preserving `apps/sync-service` as the database's only writer.

## Architecture

`apps/api-read` remains the public API and keeps `GET /api/area-paths` as a
local read query so callers can read persisted synchronization status. Its
mutating area-path routes use an injected internal HTTP client to call the
matching `apps/sync-service` JSON endpoints. The API read repository remains
read-only and does not gain write SQL.

The proxy routes pass the upstream HTTP status and JSON body through unchanged,
including successful `201` and asynchronous `202`, and upstream `404`, `409`,
and `5xx` responses. A connection or transport failure, for which no upstream
response exists, returns API Read's `503` error response.

## Routes

| Public route | Upstream route | Behavior |
| --- | --- | --- |
| `POST /api/area-paths` | `POST /api/area-paths` | Forward request JSON, status, and JSON body. |
| `PUT /api/area-paths/<id>` | `PUT /api/area-paths/<id>` | Forward request JSON, status, and JSON body. |
| `DELETE /api/area-paths/<id>` | `DELETE /api/area-paths/<id>` | Forward status and body; preserve `204`. |
| `POST /api/area-paths/<id>/sync` | `POST /api/area-paths/<id>/sync` | Forward status and body; preserve async `202`. |

`GET /api/area-paths` remains local. Other existing read routes remain
unchanged.

## Configuration and CORS

`SYNC_SERVICE_BASE_URL` configures the upstream origin and defaults to
`http://127.0.0.1:5000`. CORS allows configured origins and advertises
`GET, POST, PUT, DELETE, OPTIONS` so browser callers can use the proxied
operations.

## Testing

Tests use an injected fake HTTP transport/client and verify each forwarding
route, verbatim forwarding of upstream success and error status/body, the
transport-failure `503`, local GET behavior, and CORS/preflight behavior. The
existing read-only SQL guardrail remains green, proving API Read does not
introduce write statements.

## Scope limits

No changes are made to `apps/web-read`. No database write SQL, schema changes,
or changes to Sync Service route behavior are made. No commits are created.
