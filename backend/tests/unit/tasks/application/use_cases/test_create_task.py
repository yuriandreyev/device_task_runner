from unittest.mock import Mock

import pytest

from backend.tasks.application.ports import TaskRepository
from backend.tasks.application.use_cases.create_task import create_task


def test_unsupported_action_is_rejected_before_storage() -> None:
    repository = Mock(spec=TaskRepository)
    with pytest.raises(ValueError, match="Unsupported task action"):
        create_task(repository, "pc-42", "shell")
    repository.create.assert_not_called()
