# ============================================================
#  News Curator - 최초 1회 환경 구축 (setup.ps1)
# ------------------------------------------------------------
#  setup.bat 가 이 파일을 호출한다. BOM 포함 UTF-8 필수.
# ============================================================

$ErrorActionPreference = 'Stop'

# --- 콘솔 UTF-8 강제 ---
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { [Console]::InputEncoding  = [System.Text.UTF8Encoding]::new($false) } catch {}
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8       = '1'
try { chcp 65001 > $null } catch {}

# --- 경로 고정 ---
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ROOT
$Host.UI.RawUI.WindowTitle = 'News Curator - 최초 환경 구축 (setup.ps1)'

function Fail($msg) { Write-Host "[오류] $msg" -ForegroundColor Red; exit 1 }

Write-Host ''
Write-Host '=============================================================='
Write-Host '  News Curator - 최초 1회 환경 구축 (setup.ps1)'
Write-Host '=============================================================='
Write-Host "  프로젝트 루트 : $ROOT"
Write-Host '=============================================================='
Write-Host ''

# --- [1/5] Python ---
Write-Host '[1/5] Python 버전 확인 (3.12+ 권장)'
Write-Host '--------------------------------------------------------------'
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Host '[오류] python 명령을 찾을 수 없습니다.'
    Write-Host '       https://www.python.org/downloads/ 에서 Python 3.12 설치 후'
    Write-Host '       설치 시 "Add Python to PATH" 체크 후 다시 실행하세요.'
    exit 1
}
& python --version
Write-Host ''

# --- [2/5] venv ---
Write-Host '[2/5] backend\.venv 생성 + requirements.txt 설치'
Write-Host '--------------------------------------------------------------'
$venvPy = Join-Path $ROOT 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    Write-Host '  생성 중: backend\.venv'
    & python -m venv (Join-Path $ROOT 'backend\.venv')
    if ($LASTEXITCODE -ne 0) { Fail 'venv 생성 실패' }
} else {
    Write-Host '  [skip] backend\.venv 가 이미 존재'
}

Write-Host '  pip 업그레이드'
& $venvPy -m pip install --upgrade pip | Out-Null

Write-Host '  requirements.txt 설치 (수 분 소요)'
& $venvPy -m pip install -r (Join-Path $ROOT 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { Fail '의존성 설치 실패. 네트워크/프록시를 확인하세요.' }
Write-Host '  [OK] 백엔드 의존성 설치 완료'
Write-Host ''

# --- [3/5] frontend ---
Write-Host '[3/5] frontend\node_modules 설치'
Write-Host '--------------------------------------------------------------'
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host '[오류] npm 명령을 찾을 수 없습니다.'
    Write-Host '       https://nodejs.org/ 에서 Node.js 20 LTS 설치 후 재실행하세요.'
    exit 1
}
Push-Location (Join-Path $ROOT 'frontend')
try {
    & npm install
    if ($LASTEXITCODE -ne 0) { Fail 'npm install 실패' }
} finally { Pop-Location }
Write-Host '  [OK] 프론트엔드 의존성 설치 완료'
Write-Host ''

# --- [4/5] .env ---
Write-Host '[4/5] backend\.env 준비'
Write-Host '--------------------------------------------------------------'
$envFile    = Join-Path $ROOT 'backend\.env'
$envExample = Join-Path $ROOT 'backend\.env.example'
if (Test-Path $envFile) {
    Write-Host '  [skip] backend\.env 가 이미 존재'
} elseif (Test-Path $envExample) {
    Copy-Item $envExample $envFile
    Write-Host '  [OK] .env.example -> .env 복사 완료'
} else {
    Fail 'backend\.env.example 이 없습니다. 리포지토리가 불완전합니다.'
}
Write-Host ''

# --- [5/5] 다음 단계 ---
Write-Host '=============================================================='
Write-Host '  [5/5] 다음 단계 - 아직 끝나지 않았습니다!'
Write-Host '--------------------------------------------------------------'
Write-Host ''
Write-Host '  1) API 키 입력 (필수): 메모장으로 backend\.env 열고 채우기'
Write-Host '       SECRET_KEY=          (필수) 임의 32바이트 이상 문자열'
Write-Host '       NAVER_CLIENT_ID=     (필수) https://developers.naver.com/apps/'
Write-Host '       NAVER_CLIENT_SECRET= (필수) 위와 동일'
Write-Host '       OPENAI_API_KEY=      (선택) https://platform.openai.com/api-keys'
Write-Host ''
Write-Host '     SECRET_KEY 생성 도우미:'
Write-Host '       python -c "import secrets; print(secrets.token_hex(32))"'
Write-Host ''
Write-Host '  2) Ollama 설치 + 모델 다운로드 (필수):'
Write-Host '       https://ollama.com/download 에서 설치'
Write-Host '       ollama pull llama3      (4.7 GB, 1회만)'
Write-Host '       ollama serve            (별도 터미널에 상주)'
Write-Host ''
Write-Host '  3) Docker Desktop 이 실행 중인지 확인'
Write-Host ''
Write-Host '  4) 위 준비가 끝나면: .\run_all.bat'
Write-Host ''
Write-Host '=============================================================='
exit 0
