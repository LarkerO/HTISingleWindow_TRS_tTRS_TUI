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


def test_version_local_file_and_explicit_config_precedence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.local.toml").write_text('version = "9.8.7"\n', encoding="utf-8")
    config = Config.load(None)
    assert config.version == "9.8.7"
    assert config.window_title == (
        "氢气工艺服务器交通信息单一窗口 HydCraft Server Transit Information Single Windows tTRS | 9.8.7"
    )
    explicit = tmp_path / "operator.toml"
    explicit.write_text('version = "2.1.0-local"\n', encoding="utf-8")
    assert Config.load(explicit).version == "2.1.0-local"


@pytest.mark.parametrize("version", ["", "0.4.0\nBAD", 123, "bad version"])
def test_invalid_title_versions_are_rejected(version):
    with pytest.raises(ValueError):
        Config(version=version)
