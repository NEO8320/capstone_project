@echo off
chcp 65001 >nul 2>&1
title News Curator - 통합 실행 스크립트

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║           News Curator - AI 뉴스 큐레이팅 서비스            ║
echo ║                    통합 실행 스크립트                        ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

echo ──────────────────────────────────────────────────────────────
echo  [사전 확인] 아래 프로그램이 실행 중인지 확인해 주세요!
echo ──────────────────────────────────────────────────────────────
echo.
echo   1. Docker Desktop  - PostgreSQL + Redis 컨테이너용
echo   2. Ollama           - 로컬 Llama 3 LLM 서버용
echo.
echo  ※ Docker가 꺼져 있으면 DB/Redis 연결이 실패합니다.
echo  ※ Ollama가 꺼져 있으면 기사 요약/분류가 작동하지 않습니다.
echo ──────────────────────────────────────────────────────────────
echo.
pause

echo.
echo [1/4] Docker 컨테이너 시작 중 (PostgreSQL + Redis)...
echo ──────────────────────────────────────────────────────────────
cd /d "%~dp0"
docker-compose up -d
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [경고] Docker 컨테이너 시작 실패! Docker Desktop이 켜져 있는지 확인하세요.
    echo         수동으로 docker-compose up -d 를 실행해 보세요.
    echo.
)

echo.
echo [2/4] Ollama 상태 확인 중...
echo ──────────────────────────────────────────────────────────────
curl -s http://localhost:11434/api/tags >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [경고] Ollama 서버에 연결할 수 없습니다!
    echo         Ollama를 실행하고 llama3 모델이 준비되었는지 확인하세요.
    echo         (ollama run llama3)
) else (
    echo [OK] Ollama 서버가 정상 실행 중입니다.
)

echo.
echo [3/4] 백엔드 서버 시작 중 (FastAPI :8000)...
echo ──────────────────────────────────────────────────────────────
start "News Curator - Backend" cmd /k "cd /d %~dp0 && python start_backend.py"
timeout /t 3 /nobreak >nul

echo.
echo [4/4] 프론트엔드 서버 시작 중 (Vite :5173)...
echo ──────────────────────────────────────────────────────────────
start "News Curator - Frontend" cmd /k "cd /d %~dp0\frontend && npx vite --host"
timeout /t 3 /nobreak >nul

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║                   모든 서버 시작 완료!                       ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║                                                              ║
echo ║  프론트엔드:  http://localhost:5173                          ║
echo ║  백엔드 API:  http://localhost:8000                          ║
echo ║  API 문서:    http://localhost:8000/docs                     ║
echo ║                                                              ║
echo ║  종료하려면 열린 터미널 창들을 닫아 주세요.                  ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.
pause
