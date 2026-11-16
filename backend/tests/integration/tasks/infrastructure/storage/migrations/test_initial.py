import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from backend.tasks.infrastructure.models import Task

pytestmark = pytest.mark.django_db


def test_django_discovers_relocated_migration() -> None:
    loader = MigrationLoader(connection)
    migration = loader.disk_migrations[("devices", "0001_initial")]
    assert migration.__module__ == ("backend.tasks.infrastructure.storage.migrations.0001_initial")
    assert loader.graph.leaf_nodes("devices") == [("devices", "0002_alter_task_options")]
    assert ("devices", "0001_initial") in loader.applied_migrations


def test_migrations_create_claim_indexes_in_postgresql() -> None:
    assert connection.vendor == "postgresql"
    with connection.cursor() as cursor:
        constraints = connection.introspection.get_constraints(cursor, Task._meta.db_table)
    assert constraints["task_pending_idx"]["index"]
    assert constraints["task_pending_idx"]["columns"] == ["device_id", "status", "created_at", "id"]
    assert constraints["task_lease_idx"]["index"]
    assert constraints["task_lease_idx"]["columns"] == ["device_id", "status", "lease_until"]
