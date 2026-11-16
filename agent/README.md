# Polling agent

From the repository root, install the locked dependencies with `uv sync --locked`.
Start the backend, provision a device and create a task using [the API guide](../docs/TASK_API.md).
Set the agent environment to the server base URL and provisioned device credentials:

```sh
export SERVER_URL=http://127.0.0.1:8000
export DEVICE_ID=pc-42
export DEVICE_TOKEN='<device-token>'
uv run python -m agent --once
```

Omit `--once` to poll continuously; Ctrl-C stops the process. Polling and retries
wait a random 24–36 seconds. Each request uses a 5-second connection timeout and
10-second read/write/pool timeouts. HTTPS uses certificate verification; redirects
are not followed. The HTTP client does not read proxy settings from the environment.
Configuration is read from environment variables, without automatically loading `.env`.

Only `collect_system_info` is executed. Its result contains the current OS name,
OS release, logical CPU count and total physical memory in GiB (`ram_gb`, rounded
to two decimals). Unknown actions produce a terminal failed result. Collection
errors produce a diagnostic exception type without its potentially sensitive message.
The agent does not execute a shell or arbitrary commands.

The result is serialized once and retained in memory while delivery is retried.
Network errors, HTTP 408/429 and server errors retry that exact payload and claim
token before any new claim or collection. HTTP 409 discards the stale attempt and
polling continues. Other unexpected HTTP responses or malformed claims stop the
agent with exit code 1. Logs omit credentials, response bodies and collected data.

`--once` exits 0 on an empty queue, accepted result or stale attempt. It permits
three request cycles, waiting between transient failures, and exits 1 if those
retries are exhausted. Continuous mode retries transient failures without a limit.
Pending results are not persisted across process restarts; a crash can lead to
execution again after the server's lease expires. Exactly-once execution is not
promised.
