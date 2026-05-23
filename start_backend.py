"""
News Curator — 백엔드 기동 래퍼 스크립트
==========================================

이 파일은 프로젝트 루트(D:\\news-curator) 에서 실행된다고 가정한다.
`backend\\.venv\\Scripts\\python.exe start_backend.py` 처럼 **가상환경 python 으로**
직접 호출하거나, `run_all.bat` 가 자동으로 호출해 준다.

가상환경이 아닌 시스템 python 으로 실행하면 `sentence-transformers` 등 무거운
의존성이 없어 파이프라인이 첫 기사부터 조용히 롤백되는 현상이 발생하므로
(이 프로젝트에서 실제로 발생했던 버그), 아래 prelight 검사로 **명확한 에러
메시지와 함께 조기 종료** 한다.
"""

from __future__ import annotations

import sys as _sys
# Windows cp949 환경에서 UnicodeEncodeError 방지 - 어떤 실행 경로든 보장
if _sys.platform == "win32":
    try:
        _sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        _sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass  # Python <3.7 또는 stdout 비표준 시 무시

import os
import sys
from pathlib import Path

# ─── 0. 경로 고정: 이 파일이 있는 폴더를 작업 디렉터리로 ───
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)

# backend/ 를 sys.path 에 추가 — uvicorn 의 app_dir 옵션과 이중 안전망
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def _fail(msg: str, hint: str | None = None) -> None:
    print("\n" + "=" * 60)
    print(f"[start_backend] ERROR: {msg}")
    if hint:
        print(f"[start_backend] HINT : {hint}")
    print("=" * 60 + "\n")
    sys.exit(1)


# ─── 1. 가상환경 여부 확인 ───
# Windows venv 는 sys.prefix != sys.base_prefix 로 구분된다.
if sys.prefix == sys.base_prefix:
    _fail(
        "시스템 Python 으로 실행되었습니다. 가상환경 Python 을 사용해야 합니다.",
        hint=(
            'backend\\.venv\\Scripts\\python.exe start_backend.py 로 실행하거나 '
            'run_all.bat 를 사용하세요 (run_all.bat 가 자동으로 venv python 을 찾습니다).'
        ),
    )


# ─── 2. 필수 패키지 import 사전 검증 ───
# 빠짐 시 pipeline 이 조용히 실패하는 대표 케이스를 미리 잡아낸다.
_REQUIRED = ["uvicorn", "fastapi", "sqlalchemy", "asyncpg", "sentence_transformers"]
_missing: list[str] = []
for _mod in _REQUIRED:
    try:
        __import__(_mod)
    except ImportError:
        _missing.append(_mod)
if _missing:
    _fail(
        f"필수 패키지 누락: {', '.join(_missing)}",
        hint=(
            f'{sys.executable} -m pip install -r backend\\requirements.txt 로 설치 후 재시도.'
        ),
    )


# ─── 3. backend/.env 존재 확인 ───
if not (BACKEND_DIR / ".env").is_file():
    _fail(
        "backend\\.env 파일이 없습니다.",
        hint="copy backend\\.env.example backend\\.env 로 복사한 뒤 API 키를 채우세요.",
    )


# ─── 4. UTF-8 콘솔 강제 (Windows cp949 한글 깨짐 방지) ───
os.environ.setdefault("PYTHONIOENCODING", "utf-8")


# ─── 5. Uvicorn 기동 ───
if __name__ == "__main__":
    import uvicorn

    print(f"[start_backend] ROOT         = {ROOT}")
    print(f"[start_backend] Python       = {sys.executable}")
    print(f"[start_backend] Uvicorn host = 0.0.0.0:8000 (reload=True)")
    print("[start_backend] 서버 기동 중...\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        app_dir="backend",
    )
