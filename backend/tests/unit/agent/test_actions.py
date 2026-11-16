import os
import platform
from types import SimpleNamespace
from unittest.mock import patch

import psutil
import pytest

from agent.actions import collect_system_info


def test_collects_actual_host_information() -> None:
    result = collect_system_info()
    assert result == {
        "os": platform.system(),
        "os_version": platform.release(),
        "cpu_count": os.cpu_count(),
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 2),
    }


def test_collector_uses_platform_and_memory_sources() -> None:
    with (
        patch("agent.actions.platform.system", return_value="TestOS"),
        patch("agent.actions.platform.release", return_value="1.2.3"),
        patch("agent.actions.os.cpu_count", return_value=7),
        patch(
            "agent.actions.psutil.virtual_memory", return_value=SimpleNamespace(total=12 * 1024**3)
        ),
    ):
        assert collect_system_info() == {
            "os": "TestOS",
            "os_version": "1.2.3",
            "cpu_count": 7,
            "ram_gb": 12.0,
        }


def test_missing_cpu_count_is_an_explicit_collection_failure() -> None:
    with patch("agent.actions.os.cpu_count", return_value=None), pytest.raises(RuntimeError):
        collect_system_info()
