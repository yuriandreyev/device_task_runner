# Screencast guide

Record a 3–4 minute demo showing one task, two agents, one execution, and graceful
Redis failure. Allow extra time for the optional lease-expiry demonstration.

## Prepare before recording

Follow [the README setup](../README.md): install dependencies, start PostgreSQL
and Redis, apply migrations, create the administrator and provision `pc-42`.
Set `REDIS_URL=redis://127.0.0.1:6379/0` in `.env` before starting Django.

Keep Django running in one terminal. In a second terminal, export:

```sh
export SERVER_URL=http://127.0.0.1:8000
export DEVICE_ID=pc-42
export USER_TOKEN='<DRF-user-token>'
export DEVICE_TOKEN='<device-token>'
```

Enter credentials before recording, then clear the screen. Use a large terminal
font and two visible panes: server logs and demo commands. Stop any continuous
agents and start with an empty task queue for this device.

## 1. Introduce the project — 20 seconds

Briefly show the architecture diagram in the README and say:

> This backend sends tasks to remote desktop agents through polling. PostgreSQL
> stores tasks and results. Redis tracks recent agent activity. The supported
> action collects system information.

## 2. Create one task — 30 seconds

```sh
CREATED=$(curl --fail-with-body -sS -X POST "$SERVER_URL/api/tasks/" \
  -H "Authorization: Token $USER_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"device_id":"pc-42","action":"collect_system_info"}')

printf '%s' "$CREATED" | uv run python -m json.tool

TASK_ID=$(printf '%s' "$CREATED" |
  uv run python -c 'import json,sys; print(json.load(sys.stdin)["id"])')
```

Point out `status: "pending"` and `attempt: 0`.

## 3. Run two competing agents — 40 seconds

```sh
uv run python -m agent --once &
agent_one=$!
uv run python -m agent --once &
agent_two=$!
wait "$agent_one"
wait "$agent_two"
```

Highlight `Result accepted` from one process and `No task available` from the
other. Both processes should exit successfully.

> Both agents request work for the same device. One receives the task; the other
> finds no available task.

## 4. Read the result — 30 seconds

```sh
curl --fail-with-body -sS "$SERVER_URL/api/tasks/$TASK_ID/" \
  -H "Authorization: Token $USER_TOKEN" |
  uv run python -m json.tool
```

Highlight `status: "completed"`, `attempt: 1`, and actual OS, CPU count and RAM
values in the result.

> This task completed in one attempt. Row locking protects concurrent claims.
> A crash can still cause execution again after lease expiry, so the system does
> not promise exactly-once execution.

## 5. Show Redis presence and failure handling — 60 seconds

Read presence immediately after the agent requests:

```sh
curl --fail-with-body -sS \
  "$SERVER_URL/api/devices/$DEVICE_ID/presence/" \
  -H "Authorization: Token $USER_TOKEN"
```

Expect `online`. Explain that each authorized agent request refreshes a
90-second presence marker. Then stop Redis:

```sh
docker compose stop redis
```

Repeat step 2 to create a new task and update `TASK_ID`. Run one agent:

```sh
uv run python -m agent --once
```

Repeat the task read from step 4 and the presence read above. Show that the new
task completed while presence returns `unknown`.

> Redis is optional. Its failure affects the presence indicator, while
> PostgreSQL task delivery continues.

Restore Redis:

```sh
make redis-up
```

If showing recovery, run another agent poll and repeat the presence GET to show
`online` again. Redis restarts lose the transient markers.

## 6. Finish with verification — 20 seconds

```sh
TEST_REDIS_URL=redis://127.0.0.1:6379/15 make verify
```

If using a custom Redis host port, adjust both Redis URLs in this guide.
Show the final test summary and mention coverage for concurrent claims, expired
leases, stale tokens, identical result retries and Redis outages. See the
[test coverage map](../backend/tests/README.md) for details.

## Optional: demonstrate lease expiry

Use the [README lease-expiry example](../README.md#api-and-lease-expiry-example).
Keep other agents stopped, create a fresh task and claim it manually. Pause or
cut the 61-second wait in the recording, then show the second claim's attempt `2`
and the old token receiving `409`. Finish the current attempt using the README
commands so the demo leaves no running task behind.

To show presence expiry separately, stop agents and wait 91 seconds after their
last request. A presence GET returns `offline` when Redis is healthy; the GET
does not refresh the marker. Use a cut or time-lapse for this wait.
