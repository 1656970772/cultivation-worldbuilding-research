import dataclasses
import importlib
import sys
import types

import pytest


@dataclasses.dataclass(frozen=True)
class FakeModelConfig:
    model_id: str | None = None
    provider: str | None = None
    provider_kwargs: dict | None = None


def _install_fake_langextract(monkeypatch):
    langextract = types.ModuleType("langextract")
    factory = types.ModuleType("langextract.factory")
    factory.ModelConfig = FakeModelConfig
    langextract.factory = factory
    monkeypatch.setitem(sys.modules, "langextract", langextract)
    monkeypatch.setitem(sys.modules, "langextract.factory", factory)


def _reload_provider():
    sys.modules.pop("scripts.pipeline.minimax_provider", None)
    return importlib.import_module("scripts.pipeline.minimax_provider")


def test_build_model_config_uses_environment_key_and_default_base_url(tmp_path, monkeypatch):
    provider = _reload_provider()
    _install_fake_langextract(monkeypatch)
    monkeypatch.setattr(provider, "PLUGIN_ROOT", tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)

    config = provider.build_model_config()

    assert config == FakeModelConfig(
        model_id="MiniMax-M2.7",
        provider="openai",
        provider_kwargs={
            "api_key": "env-key",
            "base_url": "https://api.minimaxi.com/v1",
        },
    )


def test_build_model_config_environment_overrides_dotenv(tmp_path, monkeypatch):
    provider = _reload_provider()
    _install_fake_langextract(monkeypatch)
    monkeypatch.setattr(provider, "PLUGIN_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MINIMAX_API_KEY=dotenv-key",
                "MINIMAX_BASE_URL=https://dotenv.example/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://env.example/v1")

    config = provider.build_model_config(model_id="custom-minimax")

    assert config.provider == "openai"
    assert config.model_id == "custom-minimax"
    assert config.provider_kwargs["api_key"] == "env-key"
    assert config.provider_kwargs["base_url"] == "https://env.example/v1"


def test_build_model_config_reads_quoted_dotenv_values(tmp_path, monkeypatch):
    provider = _reload_provider()
    _install_fake_langextract(monkeypatch)
    monkeypatch.setattr(provider, "PLUGIN_ROOT", tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                'MINIMAX_API_KEY="dotenv-key"',
                "MINIMAX_BASE_URL='https://dotenv.example/v1'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = provider.build_model_config()

    assert config.provider == "openai"
    assert config.provider_kwargs == {
        "api_key": "dotenv-key",
        "base_url": "https://dotenv.example/v1",
    }


def test_build_model_config_accepts_configured_base_url(tmp_path, monkeypatch):
    provider = _reload_provider()
    _install_fake_langextract(monkeypatch)
    monkeypatch.setattr(provider, "PLUGIN_ROOT", tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)

    config = provider.build_model_config(base_url="https://config.example/v1")

    assert config.provider_kwargs["base_url"] == "https://config.example/v1"


def test_build_model_config_requires_minimax_api_key(tmp_path, monkeypatch):
    provider = _reload_provider()
    _install_fake_langextract(monkeypatch)
    monkeypatch.setattr(provider, "PLUGIN_ROOT", tmp_path)
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    monkeypatch.delenv("MINIMAX_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        provider.build_model_config()


def test_build_model_config_rejects_blank_environment_key(tmp_path, monkeypatch):
    provider = _reload_provider()
    _install_fake_langextract(monkeypatch)
    monkeypatch.setattr(provider, "PLUGIN_ROOT", tmp_path)
    monkeypatch.setenv("MINIMAX_API_KEY", "   ")

    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        provider.build_model_config()


def test_build_model_config_reports_missing_langextract(monkeypatch):
    provider = _reload_provider()
    monkeypatch.setenv("MINIMAX_API_KEY", "env-key")
    monkeypatch.setitem(sys.modules, "langextract", None)
    monkeypatch.setitem(sys.modules, "langextract.factory", None)

    with pytest.raises(RuntimeError, match=r"pip install langextract\[openai\]"):
        provider.build_model_config()
