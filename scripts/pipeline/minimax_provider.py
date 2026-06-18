from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


PLUGIN_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_ID = "MiniMax-M2.7"
DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _setting(
    name: str,
    env: Mapping[str, str],
    dotenv: Mapping[str, str],
    default: str = "",
) -> str:
    value = env.get(name)
    if value is not None and str(value).strip():
        return str(value).strip()
    value = dotenv.get(name)
    if value is not None and str(value).strip():
        return str(value).strip()
    return default


def _model_config_class():
    try:
        from langextract.factory import ModelConfig
    except ImportError as exc:
        raise RuntimeError(
            "Missing LangExtract OpenAI provider dependency. "
            "Install it with: pip install langextract[openai]"
        ) from exc
    return ModelConfig


def build_model_config(model_id: str = DEFAULT_MODEL_ID, base_url: str | None = None):
    dotenv = _dotenv_values(PLUGIN_ROOT / ".env")
    api_key = _setting("MINIMAX_API_KEY", os.environ, dotenv)
    if not api_key:
        raise ValueError(
            "MINIMAX_API_KEY is required. Set it in the environment or plugin .env file."
        )
    base_url = _setting(
        "MINIMAX_BASE_URL",
        os.environ,
        dotenv,
        base_url or DEFAULT_BASE_URL,
    )
    ModelConfig = _model_config_class()
    return ModelConfig(
        model_id=model_id,
        provider="openai",
        provider_kwargs={"api_key": api_key, "base_url": base_url},
    )
