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

Device authentication verifies a SHA-256 digest and device ownership. The agent
claim/result endpoints are later implementation steps and are not available yet.
