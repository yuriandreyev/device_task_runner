import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest


@pytest.mark.parametrize("empty", [True, False])
def test_module_once_runs_in_standalone_process(empty: bool) -> None:
    requests: list[tuple[str, bytes, str | None]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            content = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            requests.append((self.path, content, self.headers.get("Authorization")))
            if self.path.endswith("/claim/"):
                self.send_response(204 if empty else 200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                if not empty:
                    self.wfile.write(
                        json.dumps(
                            {
                                "id": 73,
                                "action": "collect_system_info",
                                "claim_token": "attempt-secret",
                            }
                        ).encode()
                    )
            else:
                self.send_response(200)
                self.end_headers()

        def log_message(self, format: str, *args: Any) -> None:
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = subprocess.run(
                [sys.executable, "-m", "agent", "--once"],
                env={
                    **os.environ,
                    "SERVER_URL": f"http://127.0.0.1:{server.server_port}",
                    "DEVICE_ID": "pc-42",
                    "DEVICE_TOKEN": "device-secret",
                },
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        finally:
            server.shutdown()
            thread.join(timeout=5)
    assert result.returncode == 0, result.stderr
    assert all(auth == "Bearer device-secret" for _, _, auth in requests)
    assert len(requests) == (1 if empty else 2)
    assert "secret" not in result.stdout + result.stderr
    if not empty:
        assert requests[1][0] == "/api/tasks/73/result/"
        payload = json.loads(requests[1][1])
        assert payload["status"] == "completed"
        assert payload["claim_token"] == "attempt-secret"
        assert payload["result"]["ram_gb"] > 0
        assert payload["result"]["cpu_count"] > 0
        assert payload["result"]["os"]
        assert payload["result"]["os_version"]


def test_missing_configuration_exits_with_diagnostic_without_traceback() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "agent", "--once"],
        env={**os.environ, "SERVER_URL": "", "DEVICE_TOKEN": "secret"},
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 1
    assert "SERVER_URL" in result.stderr
    assert "Traceback" not in result.stderr
    assert "secret" not in result.stderr
