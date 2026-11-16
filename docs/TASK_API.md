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
The result endpoint is a later implementation step and is not available yet.
