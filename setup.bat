@echo off
REM ============================================================
REM  News Curator — 최초 1회 환경 구축 스크립트 (setup.bat)
REM ------------------------------------------------------------
REM  역할 : 다른 데스크탑에서 clone 한 직후 단 한 번 실행하면
REM         개발 환경이 자동 구축된다. 이후에는 run_all.bat 로
REM         서비스를 기동한다.
REM
REM  수행 작업:
REM    [1/5] Python 3.12+ 확인
REM    [2/5] backend\.venv 생성 및 pip install -r backend\requirements.txt
REM    [3/5] frontend\node_modules 설치 (npm install)
REM    [4/5] backend\.env 복사 (없으면 .env.example 에서)
REM    [5/5] 다음 단계 안내 (API 키 입력 + Ollama 모델 다운로드)
REM
REM  실행:
REM    cd D:\news-curator
REM    .\setup.bat
REM ============================================================

@echo off
chcp 65001 >nul 2>&1
title News Curator - 최초 환경 구축 (setup.bat)

cd /d "%~dp0"
set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"

echo.
echo ==============================================================
echo   News Curator - 최초 1회 환경 구축 (setup.bat)
echo ==============================================================
echo   프로젝트 루트 : %ROOT%
echo ==============================================================
echo.

REM ─── [1/5] Python 버전 확인 ────────────────────────────────
echo [1/5] Python 버전 확인 (3.12+ 권장)
echo --------------------------------------------------------------
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [오류] python 명령을 찾을 수 없습니다.
    echo        https://www.python.org/downloads/ 에서 Python 3.12 설치 후
    echo        (설치 시 "Add Python to PATH" 체크) 다시 실행하세요.
    pause
    exit /b 1
)
python --version
echo.


REM ─── [2/5] 백엔드 가상환경 생성 ────────────────────────────
echo [2/5] backend\.venv 생성 + requirements.txt 설치
echo --------------------------------------------------------------
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
    echo   생성 중: backend\.venv
    python -m venv "%ROOT%\backend\.venv"
    if %ERRORLEVEL% NEQ 0 (
        echo [오류] venv 생성 실패
        pause
        exit /b 1
    )
) else (
    echo   [skip] backend\.venv 가 이미 존재
)

set "VENV_PY=%ROOT%\backend\.venv\Scripts\python.exe"

echo   pip 업그레이드
"%VENV_PY%" -m pip install --upgrade pip >nul

echo   requirements.txt 설치 (수 분 소요)
"%VENV_PY%" -m pip install -r "%ROOT%\backend\requirements.txt"
if %ERRORLEVEL% NEQ 0 (
    echo [오류] 의존성 설치 실패. 네트워크/프록시를 확인하세요.
    pause
    exit /b 1
)
echo   [OK] 백엔드 의존성 설치 완료
echo.


REM ─── [3/5] 프론트엔드 의존성 ───────────────────────────────
echo [3/5] frontend\node_modules 설치
echo --------------------------------------------------------------
where npm >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [오류] npm 명령을 찾을 수 없습니다.
    echo        https://nodejs.org/ 에서 Node.js 20 LTS 설치 후 재실행하세요.
    pause
    exit /b 1
)
pushd "%ROOT%\frontend"
call npm install
if %ERRORLEVEL% NEQ 0 (
    popd
    echo [오류] npm install 실패
    pause
    exit /b 1
)
popd
echo   [OK] 프론트엔드 의존성 설치 완료
echo.


REM ─── [4/5] .env 복사 ─────────────────────────────────────
echo [4/5] backend\.env 준비
echo --------------------------------------------------------------
if exist "%ROOT%\backend\.env" (
    echo   [skip] backend\.env 가 이미 존재
) else (
    if exist "%ROOT%\backend\.env.example" (
        copy "%ROOT%\backend\.env.example" "%ROOT%\backend\.env" >nul
        echo   [OK] .env.example -> .env 복사 완료
    ) else (
        echo [오류] backend\.env.example 이 없습니다. 리포지토리가 불완전합니다.
        pause
        exit /b 1
    )
)
echo.


REM ─── [5/5] 다음 단계 안내 ────────────────────────────────
echo ==============================================================
echo   [5/5] 다음 단계 — 아직 끝나지 않았습니다!
echo --------------------------------------------------------------
echo.
echo   1) API 키 입력 (필수):
echo      메모장 등으로 backend\.env 를 열고 아래 값을 채우세요.
echo.
echo        SECRET_KEY=          (필수) 임의 32바이트 이상 문자열
echo        NAVER_CLIENT_ID=     (필수) https://developers.naver.com/apps/
echo        NAVER_CLIENT_SECRET= (필수) 위와 동일
echo        OPENAI_API_KEY=      (선택) https://platform.openai.com/api-keys
echo.
echo      ※ SECRET_KEY 생성 도우미:
echo         python -c "import secrets; print(secrets.token_hex(32))"
echo.
echo   2) Ollama 설치 + 모델 다운로드 (필수):
echo        https://ollama.com/download 에서 설치
echo        ollama pull llama3      (4.7 GB, 1회만)
echo        ollama serve            (별도 터미널에 상주)
echo.
echo   3) Docker Desktop 이 실행 중인지 확인
echo.
echo   4) 위 준비가 끝나면 다음 명령으로 실행:
echo        .\run_all.bat
echo.
echo ==============================================================
echo.
pause
