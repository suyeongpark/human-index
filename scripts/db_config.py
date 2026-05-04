"""
DB 설정 - 스크립트용 (환경변수 또는 .env 파일에서 읽음)
"""

import os
from pathlib import Path

def _load_env():
    """프로젝트 루트의 .env 파일이 있으면 로드"""
    env_path = Path(__file__).parent.parent / ".streamlit" / "secrets.toml"
    if env_path.exists():
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                return {}
        with open(env_path, "rb") as f:
            data = tomllib.load(f)
        return data.get("database", {})
    return {}

_secrets = _load_env()

def _get(key, default=""):
    return _secrets.get(key, os.environ.get(key, default))

DB_CONFIG = {
    "dbname": _get("DB_NAME", "human_index"),
    "host": _get("DB_HOST", "localhost"),
    "port": int(_get("DB_PORT", "5432")),
    "user": _get("DB_USER", ""),
    "password": _get("DB_PASSWORD", ""),
}
