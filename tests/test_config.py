import pytest

from ttrs.config import Config, state_path


@pytest.mark.parametrize(
    "values",
    [
        {"timeout": True},
        {"timeout": float("nan")},
        {"ascii": "false"},
        {"base_url": 123},
        {"keys": {"not_an_action": "f2"}},
    ],
)
def test_invalid_config_fails_before_ui(values):
    with pytest.raises(ValueError):
        Config(**values)


def test_xdg_state_and_key_aliases(monkeypatch, tmp_path):
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("TTRS_STATE_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert state_path(False) == tmp_path / "tTRS" / "orders.sqlite3"
    assert Config(keys={"connection": "ctrl+l"}).keys["connection"] == "ctrl+l"
