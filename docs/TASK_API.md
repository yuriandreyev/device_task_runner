# Task administration API

Administrator authentication uses DRF user tokens, not the old `ADMIN_TOKEN`
environment variable. Device tokens use `Bearer` and cannot access these endpoints.

## Local setup

```sh
make db-up
make migrate
uv run python manage.py createsuperuser
uv run python manage.py drf_create_token <username>
uv run python manage.py create_demo_device pc-42
make run
```

For a regular Django user, grant the `devices.create_task` permission through
Django's user or group permissions. A staff flag alone does not grant this right.
An active user with a valid DRF token can read tasks; creation additionally requires
`devices.create_task`. Superusers have this permission through Django's standard
permission backend. Session login does not authenticate these endpoints.

## Create and read

```sh
curl -X POST http://127.0.0.1:8000/api/tasks/ \
  -H "Authorization: Token <user-token>" \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"pc-42","action":"collect_system_info"}'

curl http://127.0.0.1:8000/api/tasks/1/ \
  -H "Authorization: Token <user-token>"
```

Creation returns `201` with a `pending` task. Reading returns `200` with `id`,
`device_id`, `action`, `status`, `attempt`, `result` and `error`. Neither response
includes device credentials, token digests or the attempt's `claim_token`.
Invalid input returns `400`, missing devices/tasks return `404`, missing or invalid
user tokens return `401`, and insufficient creation permission returns `403`.

## Claim a task

Use the device token printed by `create_demo_device`, not the administrator token:

```sh
curl -X POST http://127.0.0.1:8000/api/agents/pc-42/claim/ \
  -H "Authorization: Bearer <device-token>"
```

The response is `200` with `id`, `action`, `attempt`, `claim_token` and `lease_until`,
or `204` with an empty body when no task is available. A successful claim commits
before returning, sets status to `running`, increments the attempt, generates a new
claim token and leases the task for 60 seconds. Eligible tasks are selected in
creation order; rows locked by another transaction are skipped.

A running task becomes eligible again after its lease expires. Reclaiming changes
the attempt and token. Execution may therefore repeat after a failure; exactly-once
execution is not guaranteed. Completed/failed tasks are never claimed again.

Device authentication verifies a SHA-256 digest and device ownership. Invalid or
missing credentials return `401`; requesting another device's queue returns `403`.

## Submit a result

```sh
curl -X POST http://127.0.0.1:8000/api/tasks/1/result/ \
  -H "Authorization: Bearer <device-token>" \
  -H 'Content-Type: application/json' \
  -d '{"claim_token":"<claim-token>","status":"completed","result":{"os":"Linux"}}'
```

For a failure, send `status: "failed"` and a nonempty `error` string instead of
`result`. Successful results require a JSON object; mixed result/error payloads
and unknown fields return `400`. The response is `200` with the same task fields
as the administrative read, without claim credentials.

The transaction locks the task and verifies device ownership and the current
claim token. Identical retries return `200` without changing any stored fields,
including `completed_at`; conflicting retries and stale tokens return `409`.
An expired lease still permits completion until another claim replaces the token.
Pending tasks return `409`, missing tasks `404`, another device's task `403`, and
missing/invalid device credentials `401`. Both completed and failed are terminal.

## Read device presence (optional Redis)

```sh
curl http://127.0.0.1:8000/api/devices/pc-42/presence/ \
  -H "Authorization: Token <user-token>"
```

Returns `200` with `{"device_id":"pc-42","status":"online"}` (or `offline` /
`unknown`). Any active authenticated DRF user can read, matching task-read access;
agent Bearer tokens cannot. Missing devices return `404`, invalid credentials
return `401`. No device secrets, claim tokens or task results appear here.

Successful authorized claim requests (200/204), accepted results and owned result
conflicts refresh a 90-second Redis marker. No marker in a healthy Redis means
`offline`; disabled/unreachable Redis means `unknown`. Reads do not extend TTL.
Redis errors do not change claim/result responses or PostgreSQL state. See the
root README for enabling Redis and running real integration tests.
