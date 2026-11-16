import os
import subprocess
import sys
from io import StringIO
from pathlib import Path

import httpx
import pytest
from django.contrib.auth.models import Permission, User
from django.core.management import call_command
from pytest_django.live_server_helper import LiveServer
from rest_framework.authtoken.models import Token

from backend.tasks.domain.enums import TaskStatus
from backend.tasks.infrastructure.models import Task

pytestmark = pytest.mark.django_db(transaction=True)


def test_documented_demo_two_standalone_agents_complete_one_task(live_server: LiveServer) -> None:
    provisioned = StringIO()
    call_command("create_demo_device", "pc-42", stdout=provisioned)
    device_token = provisioned.getvalue().split("device_token=", 1)[1].strip()
    user = User.objects.create_user(username="demo-operator")
    user.user_permissions.add(
        Permission.objects.get(codename="create_task", content_type__app_label="devices")
    )
    user_token = Token.objects.create(user=user).key
    headers = {"Authorization": f"Token {user_token}"}
    env = {
        **os.environ,
        "SERVER_URL": live_server.url,
        "DEVICE_ID": "pc-42",
        "DEVICE_TOKEN": device_token,
    }
    with httpx.Client(base_url=live_server.url, trust_env=False, timeout=10) as http:
        assert http.get("/health/").json() == {"status": "ok"}
        created = http.post(
            "/api/tasks/",
            headers=headers,
            json={"device_id": "pc-42", "action": "collect_system_info"},
        )
        assert created.status_code == 201
        task_id = created.json()["id"]
        processes: list[subprocess.Popen[str]] = []
        outputs: list[str] = []
        try:
            for _ in range(2):
                processes.append(
                    subprocess.Popen(
                        [sys.executable, "-m", "agent", "--once"],
                        env=env,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                    )
                )
            for process in processes:
                stdout, stderr = process.communicate(timeout=20)
                assert process.returncode == 0, stderr
                outputs.append(stdout + stderr)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
        assert sum("Result accepted" in output for output in outputs) == 1
        assert sum("No task available" in output for output in outputs) == 1
        assert all(device_token not in output and user_token not in output for output in outputs)
        response = http.get(f"/api/tasks/{task_id}/", headers=headers)
        assert response.status_code == 200
        task = response.json()
        assert task["status"] == TaskStatus.COMPLETED
        assert task["attempt"] == 1
        assert task["result"]["os"]
        assert task["result"]["os_version"]
        assert task["result"]["cpu_count"] > 0
        assert task["result"]["ram_gb"] > 0
        assert "claim_token" not in task
        assert "token_digest" not in task
        assert Task.objects.count() == 1


def test_readme_local_links_resolve_in_repository() -> None:
    import re

    root = Path(__file__).resolve().parents[4]
    for target in re.findall(r"\]\(([^)#]+)(?:#[^)]*)?\)", (root / "README.md").read_text()):
        if "://" not in target:
            assert (root / target).is_file(), target
