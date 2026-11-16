# Device Task Runner

A demo backend for issuing `collect_system_info` tasks to remote desktop agents.
Python 3.13, Django 5.2, DRF and PostgreSQL 17. The agent initiates outgoing HTTP
requests, so it can poll from behind NAT without an inbound device port.

```text
Administrator -- create/read --> Django + DRF --> PostgreSQL
                                    ^               |
                                    |      tasks, leases, results
                         claim / result
                                    |
                              Python agent
```

PostgreSQL is the source of truth. The agent only collects OS name/release,
logical CPU count and total physical RAM; it does not execute arbitrary commands.
Optional Redis stores only a short-lived presence marker. Push delivery and
background queues are outside this MVP.

## Start from a fresh checkout

Requirements: `uv`, Docker with Compose v2 (`--wait` support), `make`, and `curl`.
Run commands from the repository root. `uv` installs Python 3.13 if needed.

```sh
make sync
cp .env.example .env
```

Edit `.env`: set `DJANGO_SECRET_KEY` and `POSTGRES_PASSWORD` to separate random
values (generate each with `openssl rand -hex 32`). Keep the default database
name/user for the demo. The template contains no real credentials. Do not replace
an existing `.env` when returning to an already configured checkout.

```sh
make db-up
make migrate
uv run python manage.py createsuperuser --username demo
uv run python manage.py drf_create_token demo
uv run python manage.py create_demo_device pc-42
make run
```

The demo administrator is named `demo`. Copy the printed DRF token and the
provisioner's `device_token` into the environment in a **second terminal**:

```sh
export SERVER_URL=http://127.0.0.1:8000
export DEVICE_ID=pc-42
export USER_TOKEN='<DRF-user-token>'
export DEVICE_TOKEN='<device-token>'
curl --fail-with-body "$SERVER_URL/health/"
```

The server stays running in the first terminal. `/health/` returns
`{"status":"ok"}`; it is a liveness probe and does not query the database.
Django reads the repository `.env`, with exported variables taking precedence.
The standalone agent reads exported variables only; it does not load `.env`.

Device provisioning prints the random token once and stores only its SHA-256
digest. Repeating provisioning refuses the existing ID and preserves its token;
retain the original output for this local demo. The demo superuser can create
and read tasks. Regular active users can read with a DRF token and need the Django
`devices.create_task` permission to create; staff status alone is insufficient.
There is no `ADMIN_TOKEN` environment setting.

PostgreSQL binds to loopback. If port 5432 is occupied, change `POSTGRES_PORT` in
`.env` before starting Compose. Use `POSTGRES_HOST=127.0.0.1` for a host-run backend.
`make db-down` stops services while preserving the named data volume. Changing
credentials in `.env` does not reset an existing PostgreSQL volume's credentials.

## Two-agent demo (about two minutes after setup)

Start with the freshly provisioned device's empty queue. In the second terminal,
create exactly one task, then launch two agents for that same device:

```sh
CREATED=$(curl --fail-with-body -sS -X POST "$SERVER_URL/api/tasks/" \
  -H "Authorization: Token $USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"pc-42","action":"collect_system_info"}')
TASK_ID=$(printf '%s' "$CREATED" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
printf 'Created task %s\n' "$TASK_ID"

uv run python -m agent --once &
agent_one=$!
uv run python -m agent --once &
agent_two=$!
wait "$agent_one"
wait "$agent_two"

curl --fail-with-body -sS "$SERVER_URL/api/tasks/$TASK_ID/" \
  -H "Authorization: Token $USER_TOKEN" | uv run python -m json.tool
```

Both processes exit 0. One logs `Result accepted`, the other `No task available`.
The administrative read shows `status: "completed"`, `attempt: 1`, and real host
values in `result`: `os`, `os_version`, `cpu_count`, `ram_gb` (GiB, rounded to two
decimals). There is one successful claim and one execution for this demo task.
Task IDs are captured from the create response rather than assumed to start at 1.

For ongoing work, omit `--once`: `uv run python -m agent`. It polls every 24–36
seconds. Ctrl-C stops it. See [agent operation and retries](agent/README.md).

## API and lease-expiry example

| Operation | Authentication | Success |
| --- | --- | --- |
| `POST /api/tasks/` | `Token <user-token>` + create permission | `201`, pending task |
| `GET /api/tasks/{id}/` | `Token <user-token>` | `200`, task and result/error |
| `POST /api/agents/{device_id}/claim/` | `Bearer <device-token>` | `200`, attempt/token/lease; or empty `204` |
| `POST /api/tasks/{id}/result/` | `Bearer <device-token>` | `200`, accepted or identical retry |

[API examples and error codes](docs/TASK_API.md) include successful/failed result
payloads. Administrative responses omit device and claim credentials.

To simulate an agent disappearing, keep continuous agents stopped. Create one new
task with the `CREATED=...` and `TASK_ID=...` commands above, then claim it manually:

```sh
FIRST=$(curl --fail-with-body -sS -X POST "$SERVER_URL/api/agents/$DEVICE_ID/claim/" \
  -H "Authorization: Bearer $DEVICE_TOKEN")
OLD_TOKEN=$(printf '%s' "$FIRST" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["claim_token"])')
sleep 61
SECOND=$(curl --fail-with-body -sS -X POST "$SERVER_URL/api/agents/$DEVICE_ID/claim/" \
  -H "Authorization: Bearer $DEVICE_TOKEN")
printf '%s' "$SECOND" | uv run python -c 'import json,sys; d=json.load(sys.stdin); print("attempt:", d["attempt"])'

# The old attempt now conflicts: curl prints HTTP status 409.
printf '{"claim_token":"%s","status":"completed","result":{}}' "$OLD_TOKEN" | \
  curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$SERVER_URL/api/tasks/$TASK_ID/result/" \
    -H "Authorization: Bearer $DEVICE_TOKEN" -H 'Content-Type: application/json' --data-binary @-

NEW_TOKEN=$(printf '%s' "$SECOND" | uv run python -c 'import json,sys; print(json.load(sys.stdin)["claim_token"])')
printf '{"claim_token":"%s","status":"failed","error":"Manual lease demo finished"}' "$NEW_TOKEN" | \
  curl --fail-with-body -sS -X POST "$SERVER_URL/api/tasks/$TASK_ID/result/" \
    -H "Authorization: Bearer $DEVICE_TOKEN" -H 'Content-Type: application/json' --data-binary @-
```

The second claim has `attempt: 2` and a different token. Lease expiry alone does
not invalidate a result: before a new claim, the current token can still complete
the task. After reclaim, the old token returns `409`. Both `completed` and `failed`
are terminal. Identical retries return `200` without changing completion time;
conflicting retries return `409`.

## Guarantees and limitations

Claim uses a short PostgreSQL transaction with row locking and `SKIP LOCKED`.
It selects the oldest eligible pending/expired task, increments the attempt and
issues a fresh random token with a 60-second lease, committing before responding.
Result submission locks the row and checks the device and current claim token.

If execution succeeds but the agent crashes or cannot deliver the result, lease
expiry permits execution again: delivery can be at least once, and **exactly-once
execution is not guaranteed**. System information collection is safe to repeat.
Within a running agent, result-delivery retries reuse the same bytes and token
without collecting again. Pending results are held in memory, so restart loses
them. `--once` limits transient retries to three cycles; continuous mode keeps
retrying. HTTP 409 discards the stale attempt; other permanent HTTP errors stop
the agent. Requests have finite connection/read/write timeouts.

This is a local demonstration, using Django's development server. Production needs
TLS deployment, credential rotation, audit, rate limiting, result-size limits and
monitoring. There is no remote shell, full UEM/RBAC platform, push transport or
capacity claim for thousands of devices.

## Optional Redis presence

Presence is disabled by default and returns `unknown`. To enable it:

```sh
make redis-up
```

Set `REDIS_URL=redis://127.0.0.1:6379/0` in `.env`, then restart the Django server.
If port 6379 is occupied, set `REDIS_PORT` before starting Redis and use the same
port in `REDIS_URL`. The Compose service binds to loopback, disables disk
persistence and is optional; `make db-up` continues to start only PostgreSQL.

After an agent poll (even an empty queue), read presence with a user token:

```sh
uv run python -m agent --once
curl --fail-with-body -sS "$SERVER_URL/api/devices/$DEVICE_ID/presence/" \
  -H "Authorization: Token $USER_TOKEN"
# {"device_id":"pc-42","status":"online"}
```

`online` means an authorized claim/result request was recently observed. Redis
stores only `agent:{device_id}:online = 1` with a refreshed 90-second TTL; it never
stores tasks, claim tokens, device secrets or results. Without another agent
request, the marker expires and a healthy Redis reports `offline` (not seen
recently, rather than proof the device is powered off). A disabled/unavailable
Redis reports `unknown`. Presence reads do not refresh the TTL. Owned result
retries/conflicts count as activity; unauthenticated, wrong-device, missing-task
and malformed requests do not.

To demonstrate failure handling, `docker compose stop redis`, then run an agent
and read presence: claims/results continue, while presence returns `unknown`.
`make redis-up` restores the service. Socket/connect timeouts are 0.2 seconds,
without client retries. PostgreSQL task transactions finish before Redis updates;
presence is never part of task delivery or its guarantees.

Real Redis integration tests use unique disposable keys and require an explicit
test URL (otherwise those two tests skip):

```sh
TEST_REDIS_URL=redis://127.0.0.1:6379/15 make verify
```

These tests verify a 90-second production TTL and its refresh, then exercise real
server expiry with a one-second test TTL. Other tests cover Redis exceptions and
actual connection refusal while claiming and submitting results. Tests isolate
the application from the developer's configured Redis.

## Verification

With PostgreSQL running and `.env` configured:

```sh
make verify
# Or run individual checks:
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
uv run pytest
```

Tests use a separate PostgreSQL test database; its configured user needs database
creation permission (the local Compose user has it). Concurrency tests use real
PostgreSQL sessions, synchronized workers and row locks. The end-to-end demo test
starts two standalone agents against a live Django server and checks the result.
See [test coverage](backend/tests/README.md). `make help` lists development commands.
Real `.env` files, tokens and database dumps belong outside version control.
