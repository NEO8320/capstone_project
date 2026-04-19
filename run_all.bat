@echo off
REM ============================================================
REM  News Curator — 통합 실행 스크립트 (v2, venv-aware)
REM ------------------------------------------------------------
REM  이 배치 파일은 프로젝트 루트(D:\news-curator) 에 위치한다.
REM  실행 방법:
REM    1) 파일 탐색기에서 더블 클릭
REM    2) 또는 PowerShell / cmd 에서:
REM         cd D:\news-curator
REM         .\run_all.bat
REM
REM  이 스크립트는 다음 순서로 사전 확인을 수행한다:
REM    [0/5] 사전 확인 안내 (Docker Desktop, Ollama 실행 여부)
REM    [1/5] Docker 컨테이너 기동 (PostgreSQL + Redis)
REM    [2/5] Ollama 연결 확인 (localhost:11434)
REM    [3/5] Python 가상환경 + .env 검증
REM    [4/5] 백엔드 서버 기동 (FastAPI :8000) — 새 cmd 창
REM    [5/5] 프론트엔드 서버 기동 (Vite :5173) — 새 cmd 창
REM
REM  첫 실행이라면 먼저 setup.bat 를 실행해 환경을 구축한 뒤 이 파일을 실행한다.
REM ============================================================

@echo off
chcp 65001 >nul 2>&1
title News Curator - 통합 실행 (venv-aware v2)

REM 작업 디렉터리를 이 스크립트 위치(= 프로젝트 루트) 로 고정
cd /d "%~dp0"
set "ROOT=%~dp0"
REM 끝의 백슬래시 제거
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo ==============================================================
echo   News Curator - AI 뉴스 큐레이팅 서비스 통합 실행 (v2)
echo ==============================================================
echo   프로젝트 루트 : %ROOT%
echo ==============================================================
echo.

REM ─── [0/5] 사전 확인 안내 ─────────────────────────────────────
echo [0/5] 사전 확인 체크리스트
echo   1. Docker Desktop   - PostgreSQL + Redis 컨테이너
echo   2. Ollama           - 로컬 Llama 3 LLM 서버 (ollama serve)
echo   3. backend\.env     - NAVER/OpenAI/SECRET_KEY 입력 완료
echo   4. backend\.venv    - Python 가상환경 (setup.bat 로 생성)
echo   5. frontend\node_modules - npm install 완료 (setup.bat 로 생성)
echo.
echo   [처음이면] 먼저 .\setup.bat 를 실행해 주세요.
echo --------------------------------------------------------------
pause


REM ─── [1/5] Docker 컨테이너 기동 ─────────────────────────────
echo.
echo [1/5] Docker 컨테이너 기동 (PostgreSQL + Redis)
echo --------------------------------------------------------------
where docker >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [오류] docker 명령을 찾을 수 없습니다. Docker Desktop 설치/실행을 확인하세요.
    echo        https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)
docker-compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo [경고] Docker 컨테이너 기동 실패! Docker Desktop 이 켜져 있는지 확인하세요.
    pause
    exit /b 1
)
echo   [OK] docker-compose up -d 성공


REM ─── [2/5] Ollama 연결 확인 ─────────────────────────────────
echo.
echo [2/5] Ollama 서버 연결 확인 (http://localhost:11434)
echo --------------------------------------------------------------
curl -s -f http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   [경고] Ollama 서버에 연결할 수 없습니다.
    echo          - 설치되지 않았으면 https://ollama.com/download 에서 설치
    echo          - 별도 터미널에서 "ollama serve" 를 상주시킨 뒤 이 배치를 다시 실행
    echo          - 모델이 없으면 "ollama pull llama3" 로 최초 1회 다운로드 필요
    echo.
    set /p CONTINUE="Ollama 없이 계속하시겠습니까? (요약/분류 실패함) [y/N]: "
    if /I not "%CONTINUE%"=="y" (
        exit /b 1
    )
) else (
    echo   [OK] Ollama 정상 연결
)


REM ─── [3/5] 가상환경 + .env 검증 ─────────────────────────────
echo.
echo [3/5] Python 가상환경 + backend\.env 검증
echo --------------------------------------------------------------

REM 우선순위: backend\.venv > .venv > 시스템 python
set "VENV_PY=%ROOT%\backend\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
    set "VENV_PY=%ROOT%\.venv\Scripts\python.exe"
)
if not exist "%VENV_PY%" (
    echo   [오류] 가상환경을 찾을 수 없습니다.
    echo          backend\.venv\Scripts\python.exe 또는 .venv\Scripts\python.exe
    echo   해결 : 먼저 .\setup.bat 를 실행해 가상환경을 생성하세요.
    pause
    exit /b 1
)
echo   [OK] 가상환경 python : %VENV_PY%

REM .env 존재 여부
if not exist "%ROOT%\backend\.env" (
    echo   [오류] backend\.env 가 없습니다.
    echo          backend\.env.example 을 복사한 뒤 API 키를 입력하세요.
    echo          copy backend\.env.example backend\.env
    pause
    exit /b 1
)
echo   [OK] backend\.env 존재

REM 핵심 의존성 import 테스트 (한 줄로 통합)
"%VENV_PY%" -c "import uvicorn, fastapi, sqlalchemy, asyncpg, sentence_transformers" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo   [오류] 가상환경에 필수 패키지가 설치되어 있지 않습니다.
    echo          %VENV_PY% -m pip install -r backend\requirements.txt
    echo          또는 .\setup.bat 를 실행해 자동 설치하세요.
    pause
    exit /b 1
)
echo   [OK] 백엔드 의존성 모두 import 성공

REM frontend node_modules 확인
if not exist "%ROOT%\frontend\node_modules\.bin\vite.cmd" (
    echo   [오류] frontend\node_modules 가 없거나 vite 가 설치되지 않았습니다.
    echo          cd frontend ^&^& npm install
    echo          또는 .\setup.bat 를 실행해 자동 설치하세요.
    pause
    exit /b 1
)
echo   [OK] frontend\node_modules 정상


REM ─── [4/5] 백엔드 서버 기동 ─────────────────────────────────
echo.
echo [4/5] 백엔드 서버 기동 (FastAPI :8000)
echo --------------------------------------------------------------
REM 새 cmd 창에서 venv python 으로 start_backend.py 실행
REM   PYTHONIOENCODING=utf-8 : Windows cp949 한글 깨짐 방지
start "News Curator - Backend (FastAPI :8000)" cmd /k ^
    "cd /d %ROOT% && set PYTHONIOENCODING=utf-8 && \"%VENV_PY%\" start_backend.py"
echo   [OK] 새 창에서 백엔드 기동 시작

REM 백엔드가 뜨는 동안 잠깐 대기
timeout /t 4 /nobreak >nul


REM ─── [5/5] 프론트엔드 서버 기동 ─────────────────────────────
echo.
echo [5/5] 프론트엔드 서버 기동 (Vite :5173)
echo --------------------------------------------------------------
start "News Curator - Frontend (Vite :5173)" cmd /k ^
    "cd /d %ROOT%\frontend && npm run dev -- --host"
echo   [OK] 새 창에서 프론트엔드 기동 시작

timeout /t 3 /nobreak >nul


REM ─── 완료 안내 ────────────────────────────────────────────
echo.
echo ==============================================================
echo   모든 서버 기동 요청 완료
echo --------------------------------------------------------------
echo   프론트엔드  : http://localhost:5173
echo   백엔드 API  : http://localhost:8000
echo   API 문서    : http://localhost:8000/docs
echo --------------------------------------------------------------
echo   종료 : 열린 두 개의 cmd 창을 모두 닫으세요.
echo          (Ctrl+C 로 서버 정지 후 창 닫기)
echo ==============================================================
echo.
pause
