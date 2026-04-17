"""
YAML 설정 로더 (NFR-E03)
========================
config.yaml에서 LLM 모델 경로, 추천 가중치 등 튜닝 파라미터를 로드한다.
API 키 등 민감 정보는 .env에서, 런타임 파라미터는 config.yaml에서 관리한다.
"""

from pathlib import Path

import yaml

_config: dict | None = None


def get_yaml_config() -> dict:
    """config.yaml을 로드하여 딕셔너리로 반환한다 (싱글턴 캐싱)."""
    global _config
    if _config is not None:
        return _config

    config_path = Path(__file__).resolve().parent.parent.parent / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            _config = yaml.safe_load(f) or {}
    else:
        _config = {}
    return _config
