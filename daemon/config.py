"""Načítání konfigurace z config.yaml (s přepsáním z config.local.yaml)."""
import os
import yaml
from pathlib import Path

_DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"
_LOCAL_CONFIG_PATH = Path(__file__).parent.parent / "config.local.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_config(path: str | None = None) -> dict:
    cfg_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    with open(cfg_path) as f:
        cfg = yaml.safe_load(f)
    if _LOCAL_CONFIG_PATH.exists():
        with open(_LOCAL_CONFIG_PATH) as f:
            local = yaml.safe_load(f) or {}
        cfg = _deep_merge(cfg, local)
    env_db = os.environ.get("CT_DB_PATH")
    if env_db:
        cfg.setdefault("database", {})["path"] = env_db
    return cfg
