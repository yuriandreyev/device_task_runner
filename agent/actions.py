import os
import platform

import psutil


def collect_system_info() -> dict[str, object]:
    cpu_count = os.cpu_count()
    if cpu_count is None:
        raise RuntimeError("CPU count is unavailable")
    return {
        "os": platform.system(),
        "os_version": platform.release(),
        "cpu_count": cpu_count,
        "ram_gb": round(psutil.virtual_memory().total / 1024**3, 2),
    }
