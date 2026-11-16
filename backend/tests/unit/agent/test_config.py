import pytest

from agent.config import Config


def test_config_normalizes_base_url_and_does_not_expose_token() -> None:
    config = Config.from_env(
        {
            "SERVER_URL": "https://example.test/prefix/",
            "DEVICE_ID": "pc-42",
            "DEVICE_TOKEN": "secret",
        }
    )
    assert config.server_url == "https://example.test/prefix"
    assert "secret" not in repr(config)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("SERVER_URL", ""),
        ("SERVER_URL", "file:///tmp/example"),
        ("SERVER_URL", "https://secret@example.test"),
        ("SERVER_URL", "https://example.test/?secret=value"),
        ("SERVER_URL", "https://example.test/#secret"),
        ("SERVER_URL", "http://example.test:bad"),
        ("DEVICE_ID", ""),
        ("DEVICE_ID", "../pc"),
        ("DEVICE_ID", "x" * 65),
        ("DEVICE_TOKEN", ""),
        ("DEVICE_TOKEN", "secret\nheader"),
    ],
)
def test_invalid_configuration_is_rejected_without_echoing_values(key: str, value: str) -> None:
    env = {"SERVER_URL": "https://example.test", "DEVICE_ID": "pc-42", "DEVICE_TOKEN": "secret"}
    env[key] = value
    with pytest.raises(ValueError) as exc:
        Config.from_env(env)
    assert "secret" not in str(exc.value)
