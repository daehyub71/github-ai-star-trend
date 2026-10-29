"""core.config — 시크릿은 환경변수로만 받고, 화면·로그에 남기지 않는다 (SPEC NFR-8)."""

from pathlib import Path

import pytest

from startrend.core import config


def test_config_defaults_to_project_dirs(tmp_path):
    s = config.load_settings(env={}, root=tmp_path)
    assert s.data_dir == tmp_path / "data"
    assert s.work_dir == tmp_path / ".work"
    assert s.github_token is None


def test_config_reads_env_overrides(tmp_path):
    env = {
        "GITHUB_TOKEN": "ghp_secret",
        "STARTREND_DATA_DIR": str(tmp_path / "d"),
        "STARTREND_WORK_DIR": str(tmp_path / "w"),
    }
    s = config.load_settings(env=env, root=tmp_path)
    assert s.github_token == "ghp_secret"
    assert s.data_dir == Path(tmp_path / "d")
    assert s.work_dir == Path(tmp_path / "w")


def test_config_blank_token_is_none(tmp_path):
    s = config.load_settings(env={"GITHUB_TOKEN": "  "}, root=tmp_path)
    assert s.github_token is None


def test_config_repr_masks_token(tmp_path):
    s = config.load_settings(env={"GITHUB_TOKEN": "ghp_secret"}, root=tmp_path)
    assert "ghp_secret" not in repr(s)
    assert "ghp_secret" not in str(s)


def test_config_require_token_raises_without_token(tmp_path):
    s = config.load_settings(env={}, root=tmp_path)
    with pytest.raises(config.ConfigError) as e:
        s.require_github_token()
    assert "GITHUB_TOKEN" in str(e.value)


def test_config_require_token_returns_token(tmp_path):
    s = config.load_settings(env={"GITHUB_TOKEN": "ghp_secret"}, root=tmp_path)
    assert s.require_github_token() == "ghp_secret"


def test_config_reads_only_the_project_anthropic_key(tmp_path):
    # NFR-8: ANTHROPIC_API_KEY 는 다른 프로그램(Claude Code 등)이 집어 쓸 수 있어 이 프로젝트는 읽지 않는다
    other = config.load_settings(env={"ANTHROPIC_API_KEY": "sk-ant-other"}, root=tmp_path)
    assert other.anthropic_key is None
    s = config.load_settings(env={"STARTREND_ANTHROPIC_API_KEY": " sk-ant-mine "}, root=tmp_path)
    assert s.require_anthropic_key() == "sk-ant-mine"
    assert "sk-ant-mine" not in repr(s) and "sk-ant-mine" not in str(s)


def test_config_require_anthropic_key_names_the_variable(tmp_path):
    with pytest.raises(config.ConfigError) as e:
        config.load_settings(env={}, root=tmp_path).require_anthropic_key()
    assert "STARTREND_ANTHROPIC_API_KEY" in str(e.value)


def test_config_reads_notion_token_and_hides_it(tmp_path):
    s = config.load_settings(env={"NOTION_TOKEN": " ntn_mine "}, root=tmp_path)
    assert s.require_notion_token() == "ntn_mine"
    assert "ntn_mine" not in repr(s) and "ntn_mine" not in str(s)
    with pytest.raises(config.ConfigError) as e:
        config.load_settings(env={}, root=tmp_path).require_notion_token()
    assert "NOTION_TOKEN" in str(e.value)


def test_config_reads_tavily_key_and_hides_it(tmp_path):
    s = config.load_settings(env={"STARTREND_TAVILY_API_KEY": " tvly-mine "}, root=tmp_path)
    assert s.require_tavily_key() == "tvly-mine"
    assert "tvly-mine" not in repr(s) and "tvly-mine" not in str(s)
    with pytest.raises(config.ConfigError) as e:
        config.load_settings(env={}, root=tmp_path).require_tavily_key()
    assert "STARTREND_TAVILY_API_KEY" in str(e.value)


def test_config_default_root_is_project_root():
    s = config.load_settings(env={})
    assert (s.data_dir.parent / "pyproject.toml").exists()
