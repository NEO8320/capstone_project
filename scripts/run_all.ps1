# ============================================================
#  News Curator - 통합 실행 (run_all.ps1, v3 PowerShell)
# ------------------------------------------------------------
#  run_all.bat 가 이 파일을 호출한다. BOM 포함 UTF-8 필수.
# ============================================================

$ErrorActionPreference = 'Stop'

try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false) } catch {}
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8       = '1'
try { chcp 65001 > $null } catch {}

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ROOT
$Host.UI.RawUI.WindowTitle = 'News Curator - 통합 실행 (run_all.ps1)'

function Fail($msg) { Write-Host "[오류] $msg" -ForegroundColor Red; exit 1 }

Write-Host ''
Write-Host '=============================================================='
Write-Host '  News Curator - AI 뉴스 큐레이팅 서비스 통합 실행 (v3)'
Write-Host '=============================================================='
Write-Host "  프로젝트 루트 : $ROOT"
Write-Host '=============================================================='
Write-Host ''

# --- [0/5] 사전 확인 ---
Write-Host '[0/5] 사전 확인 체크리스트'
Write-Host '  1. Docker Desktop   - PostgreSQL + Redis 컨테이너'
Write-Host '  2. Ollama           - 로컬 Llama 3 LLM 서버 (ollama serve)'
Write-Host '  3. backend\.env     - NAVER/OpenAI/SECRET_KEY 입력 완료'
Write-Host '  4. backend\.venv    - Python 가상환경 (setup.bat 로 생성)'
Write-Host '  5. frontend\node_modules - npm install 완료'
Write-Host ''
Write-Host '  [처음이면] 먼저 .\setup.bat 를 실행해 주세요.'
Write-Host '--------------------------------------------------------------'
Read-Host '계속하려면 Enter 키를 누르세요'

# --- [1/5] Docker ---
Write-Host ''
Write-Host '[1/5] Docker 컨테이너 기동 (PostgreSQL + Redis)'
Write-Host '--------------------------------------------------------------'
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host '[오류] docker 명령을 찾을 수 없습니다.'
    Write-Host '       Docker Desktop 설치/실행을 확인하세요.'
    Write-Host '       https://www.docker.com/products/docker-desktop/'
    exit 1
}
& docker-compose up -d
if ($LASTEXITCODE -ne 0) { Fail 'Docker 컨테이너 기동 실패. Docker Desktop 이 켜져 있는지 확인하세요.' }
Write-Host '  [OK] docker-compose up -d 성공'

# --- [2/5] Ollama ---
Write-Host ''
Write-Host '[2/5] Ollama 서버 연결 확인 (http://localhost:11434)'
Write-Host '--------------------------------------------------------------'
$ollamaOk = $false
try {
    $r = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { $ollamaOk = $true }
} catch { $ollamaOk = $false }

if (-not $ollamaOk) {
    Write-Host '  [경고] Ollama 서버에 연결할 수 없습니다.'
    Write-Host '         - 설치되지 않았으면 https://ollama.com/download 에서 설치'
    Write-Host '         - 별도 터미널에서 "ollama serve" 상주 후 다시 실행'
    Write-Host '         - 모델이 없으면 "ollama pull llama3" 로 최초 1회 다운로드'
    $cont = Read-Host 'Ollama 없이 계속하시겠습니까? (요약/분류 실패함) [y/N]'
    if ($cont -notmatch '^(y|Y)$') { exit 1 }
} else {
    Write-Host '  [OK] Ollama 정상 연결'
}

# --- [3/5] venv + .env ---
Write-Host ''
Write-Host '[3/5] Python 가상환경 + backend\.env 검증'
Write-Host '--------------------------------------------------------------'

$venvPy = Join-Path $ROOT 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { $venvPy = Join-Path $ROOT '.venv\Scripts\python.exe' }
if (-not (Test-Path $venvPy)) {
    Write-Host '  [오류] 가상환경을 찾을 수 없습니다.'
    Write-Host '         backend\.venv\Scripts\python.exe 또는 .venv\Scripts\python.exe'
    Write-Host '  해결 : 먼저 .\setup.bat 를 실행해 가상환경을 생성하세요.'
    exit 1
}
Write-Host "  [OK] 가상환경 python : $venvPy"

if (-not (Test-Path (Join-Path $ROOT 'backend\.env'))) {
    Write-Host '  [오류] backend\.env 가 없습니다.'
    Write-Host '         backend\.env.example 을 복사한 뒤 API 키를 입력하세요.'
    exit 1
}
Write-Host '  [OK] backend\.env 존재'

& $venvPy -c "import uvicorn, fastapi, sqlalchemy, asyncpg, sentence_transformers" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host '  [오류] 가상환경에 필수 패키지가 설치되어 있지 않습니다.'
    Write-Host "         $venvPy -m pip install -r backend\requirements.txt"
    Write-Host '         또는 .\setup.bat 를 실행해 자동 설치하세요.'
    exit 1
}
Write-Host '  [OK] 백엔드 의존성 모두 import 성공'

if (-not (Test-Path (Join-Path $ROOT 'frontend\node_modules\.bin\vite.cmd'))) {
    Write-Host '  [오류] frontend\node_modules 가 없거나 vite 가 설치되지 않았습니다.'
    Write-Host '         cd frontend && npm install   또는 .\setup.bat'
    exit 1
}
Write-Host '  [OK] frontend\node_modules 정상'

# --- [4/5] 백엔드 새 창 ---
Write-Host ''
Write-Host '[4/5] 백엔드 서버 기동 (FastAPI :8000)'
Write-Host '--------------------------------------------------------------'

# 자식 cmd 창도 UTF-8 로 시작.
# PYTHONIOENCODING / PYTHONUTF8 은 이 PowerShell 부모 프로세스에서 이미 $env:* 로
# 설정되어 있으므로 자식 cmd 가 자동 상속한다. cmd 내부에서 `set PYTHONUTF8=1`
# 같은 인라인 set 을 쓰면 cmd 의 greedy 파싱이 값 끝에 공백을 붙여
# `Fatal Python error: invalid PYTHONUTF8 environment variable value` 가 발생하므로
# 절대 추가하지 말 것 (참고: 이전 v3 초기 버전 버그).
$backendCmd = "chcp 65001 >nul && title News Curator - Backend (FastAPI :8000) && cd /d `"$ROOT`" && `"$venvPy`" start_backend.py"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $backendCmd | Out-Null
Write-Host '  [OK] 새 창에서 백엔드 기동 시작'
Start-Sleep -Seconds 4

# --- [5/5] 프론트엔드 새 창 ---
Write-Host ''
Write-Host '[5/5] 프론트엔드 서버 기동 (Vite :5173)'
Write-Host '--------------------------------------------------------------'
$frontendCmd = "chcp 65001 >nul && title News Curator - Frontend (Vite :5173) && cd /d `"$ROOT\frontend`" && npm run dev -- --host"
Start-Process -FilePath 'cmd.exe' -ArgumentList '/k', $frontendCmd | Out-Null
Write-Host '  [OK] 새 창에서 프론트엔드 기동 시작'
Start-Sleep -Seconds 3

# --- 완료 ---
Write-Host ''
Write-Host '=============================================================='
Write-Host '  모든 서버 기동 요청 완료'
Write-Host '--------------------------------------------------------------'
Write-Host '  프론트엔드  : http://localhost:5173'
Write-Host '  백엔드 API  : http://localhost:8000'
Write-Host '  API 문서    : http://localhost:8000/docs'
Write-Host '--------------------------------------------------------------'
Write-Host '  종료 : 열린 두 개의 cmd 창을 모두 닫으세요.'
Write-Host '         (Ctrl+C 로 서버 정지 후 창 닫기)'
Write-Host '=============================================================='
exit 0
