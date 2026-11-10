"""Loads versioned YAML configs (configs/*.yaml). Override the directory with CONFIG_DIR."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml


def config_dir() -> Path:
    override = os.environ.get("CONFIG_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "configs"


@lru_cache
def load_config(name: str) -> dict[str, Any]:
    path = config_dir() / f"{name}.yaml"
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def routing_config() -> dict[str, Any]:
    return load_config("routing")


def reward_config() -> dict[str, Any]:
    return load_config("reward")
