"""统一配置加载: sources.yaml (可分享) + secrets.yaml (本地密钥, 不入库) 深度合并。"""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "sources.yaml"
DEFAULT_SECRETS = PROJECT_ROOT / "config" / "secrets.yaml"


def _merge(base: dict, override: dict) -> dict:
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


def load_config(config_path=None, secrets_path=None) -> dict:
    """加载 sources.yaml; 若存在 secrets.yaml 则合并覆盖 (secrets 优先)。"""
    cfg_path = Path(config_path) if config_path else DEFAULT_CONFIG
    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    sec_path = Path(secrets_path) if secrets_path else DEFAULT_SECRETS
    if sec_path.exists():
        sec = yaml.safe_load(sec_path.read_text(encoding="utf-8")) or {}
        cfg = _merge(cfg, sec)
    return cfg
