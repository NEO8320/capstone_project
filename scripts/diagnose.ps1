# ============================================================
#  News Curator - 진단 스크립트 (diagnose.ps1)
# ------------------------------------------------------------
#  "피드를 불러오는 데 실패했습니다" 같은 증상이 보일 때
#  어느 레이어가 깨졌는지 한 번에 확인한다.
#
#  사용:  .\diagnose.bat   또는   powershell -File scripts\diagnose.ps1
# ============================================================

$ErrorActionPreference = 'Continue'

try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
try { chcp 65001 > $null } catch {}

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ROOT

# ── 색상 헬퍼 ──
function Pass($name, $detail) { Write-Host ("  [PASS] {0,-30} {1}" -f $name, $detail) -ForegroundColor Green }
function Warn($name, $detail) { Write-Host ("  [WARN] {0,-30} {1}" -f $name, $detail) -ForegroundColor Yellow }
function Fail($name, $detail) { Write-Host ("  [FAIL] {0,-30} {1}" -f $name, $detail) -ForegroundColor Red }
function Info($name, $detail) { Write-Host ("  [INFO] {0,-30} {1}" -f $name, $detail) -ForegroundColor Cyan }

Write-Host ''
Write-Host '=============================================================='
Write-Host '  News Curator - 진단 (diagnose.ps1)'
Write-Host '=============================================================='
Write-Host "  프로젝트 루트 : $ROOT"
Write-Host '=============================================================='

$score = @{ pass = 0; warn = 0; fail = 0 }
$hints = New-Object System.Collections.ArrayList

# ============================================================
# 1. Docker
# ============================================================
Write-Host ''
Write-Host '[1] Docker'
Write-Host '--------------------------------------------------------------'

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail 'docker CLI' '명령을 찾을 수 없음'
    $score.fail++
    [void]$hints.Add('Docker Desktop 을 설치하세요: https://www.docker.com/products/docker-desktop/')
} else {
    Pass 'docker CLI' (& docker --version 2>&1)
    $score.pass++

    $dockerInfo = & docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Fail 'docker daemon' 'Docker Desktop 이 실행 중이 아닙니다'
        $score.fail++
        [void]$hints.Add('Docker Desktop 을 시작하고 시스템 트레이의 고래 아이콘이 안정될 때까지 기다리세요')
    } else {
        Pass 'docker daemon' '정상 동작 중'
        $score.pass++

        # 컨테이너 상태
        $psOutput = & docker ps --format '{{.Names}}|{{.Status}}' 2>&1
        $pgRunning = $psOutput | Where-Object { $_ -like 'news_curator_db*' -or $_ -like '*postgres*' }
        $redisRunning = $psOutput | Where-Object { $_ -like 'news_curator_redis*' -or $_ -like '*redis*' }

        if ($pgRunning) {
            Pass 'postgres container' ($pgRunning -join ', ')
            $score.pass++
        } else {
            Fail 'postgres container' '실행 중이 아닙니다'
            $score.fail++
            [void]$hints.Add('docker-compose up -d 를 실행하거나 .\run_all.bat 를 다시 실행하세요')
        }

        if ($redisRunning) {
            Pass 'redis container' ($redisRunning -join ', ')
            $score.pass++
        } else {
            Warn 'redis container' '실행 중이 아닙니다 (캐시 비활성으로 동작)'
            $score.warn++
            [void]$hints.Add('Redis 가 없으면 캐시가 비활성화되며 응답이 느려집니다. docker-compose up -d redis')
        }
    }
}

# ============================================================
# 2. PostgreSQL 포트 (5432)
# ============================================================
Write-Host ''
Write-Host '[2] PostgreSQL 연결 (localhost:5432)'
Write-Host '--------------------------------------------------------------'

$pgPort = $null
try {
    $pgPort = Test-NetConnection -ComputerName 'localhost' -Port 5432 -InformationLevel Quiet -WarningAction SilentlyContinue
} catch {}

if ($pgPort) {
    Pass 'TCP 5432' '연결 가능'
    $score.pass++
} else {
    Fail 'TCP 5432' '연결 불가 - postgres 컨테이너가 떠 있어야 함'
    $score.fail++
    [void]$hints.Add('postgres 컨테이너가 정상이라면: docker logs news_curator_db 로 원인 확인')
}

# ============================================================
# 3. 백엔드 (FastAPI :8000)
# ============================================================
Write-Host ''
Write-Host '[3] 백엔드 (http://localhost:8000)'
Write-Host '--------------------------------------------------------------'

$backendOk = $false
$healthBody = $null
try {
    $resp = Invoke-WebRequest -Uri 'http://localhost:8000/health' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        $backendOk = $true
        $healthBody = $resp.Content | ConvertFrom-Json
    }
} catch {}

if ($backendOk) {
    Pass 'GET /health' "status=$($healthBody.status)  redis=$($healthBody.redis_connected)"
    $score.pass++

    # DB 연결 확인을 위해 보호 endpoint 호출 (401 이면 DB OK, 500 이면 DB 깨짐)
    try {
        $feedResp = Invoke-WebRequest -Uri 'http://localhost:8000/api/feed' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        $code = $feedResp.StatusCode
    } catch {
        $code = $_.Exception.Response.StatusCode.value__
    }
    if ($code -eq 401) {
        Pass 'GET /api/feed' '401 (인증 필요) - DB/백엔드 정상'
        $score.pass++
    } elseif ($code -eq 500) {
        Fail 'GET /api/feed' '500 (서버 오류) - DB 연결이 깨졌을 가능성 큼'
        $score.fail++
        [void]$hints.Add('백엔드 cmd 창에서 "[Startup] DB 초기화" 로그를 확인하세요. "최종 실패" 가 있다면 postgres 가 죽었거나 .env 의 DATABASE_URL 비밀번호가 docker-compose 와 다릅니다')
    } else {
        Warn 'GET /api/feed' "예상치 못한 상태코드: $code"
        $score.warn++
    }
} else {
    Fail 'GET /health' '백엔드가 응답하지 않음'
    $score.fail++
    [void]$hints.Add('백엔드 cmd 창("News Curator - Backend") 이 떠 있는지 확인. 즉시 닫혔다면 .\backend\.venv\Scripts\python.exe start_backend.py 를 직접 실행해 로그 확인')
}

# ============================================================
# 4. 프론트엔드 (Vite :5173)
# ============================================================
Write-Host ''
Write-Host '[4] 프론트엔드 (http://localhost:5173)'
Write-Host '--------------------------------------------------------------'

$frontendOk = $false
try {
    $resp = Invoke-WebRequest -Uri 'http://localhost:5173/' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { $frontendOk = $true }
} catch {}

if ($frontendOk) {
    Pass 'GET /' '200 OK'
    $score.pass++
} else {
    Warn 'GET /' '응답 없음 - 프론트엔드 cmd 창이 떠 있는지 확인'
    $score.warn++
}

# ============================================================
# 5. Ollama (:11434) - LLM 요약/분류
# ============================================================
Write-Host ''
Write-Host '[5] Ollama (http://localhost:11434)'
Write-Host '--------------------------------------------------------------'

$ollamaOk = $false
$models = $null
try {
    $resp = Invoke-WebRequest -Uri 'http://localhost:11434/api/tags' -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) {
        $ollamaOk = $true
        $models = ($resp.Content | ConvertFrom-Json).models | ForEach-Object { $_.name }
    }
} catch {}

if ($ollamaOk) {
    Pass 'GET /api/tags' '응답 정상'
    $score.pass++
    if ($models -and ($models -match 'llama3')) {
        Pass 'llama3 모델' ($models -join ', ')
        $score.pass++
    } else {
        Warn 'llama3 모델' '없음 - LLM 요약 실패 → 크롤링은 되지만 요약/분류 폴백 사용'
        $score.warn++
        [void]$hints.Add('ollama pull llama3 로 모델 다운로드 (4.7 GB)')
    }
} else {
    Warn 'Ollama 서버' '연결 불가 - LLM 요약/분류 실패. 기사는 description 으로 폴백'
    $score.warn++
    [void]$hints.Add('별도 터미널에서 ollama serve 를 실행하세요')
}

# ============================================================
# 6. backend\.env 키
# ============================================================
Write-Host ''
Write-Host '[6] backend\.env 환경 변수'
Write-Host '--------------------------------------------------------------'

$envPath = Join-Path $ROOT 'backend\.env'
if (-not (Test-Path $envPath)) {
    Fail 'backend\.env' '파일이 없습니다'
    $score.fail++
    [void]$hints.Add('copy backend\.env.example backend\.env 후 API 키 입력')
} else {
    $envContent = Get-Content $envPath -Raw -ErrorAction SilentlyContinue
    foreach ($key in @('SECRET_KEY', 'NAVER_CLIENT_ID', 'NAVER_CLIENT_SECRET')) {
        if ($envContent -match "(?m)^$key\s*=\s*(.+)") {
            $val = $matches[1].Trim().Trim('"').Trim("'")
            if ($val -and $val -notmatch '^(your-|change-?me|placeholder|xxx|<.*>)$' -and $val.Length -ge 8) {
                Pass $key "설정됨 (길이 $($val.Length))"
                $score.pass++
            } else {
                Fail $key "값이 비어있거나 placeholder ('$val')"
                $score.fail++
                [void]$hints.Add("backend\.env 의 $key 에 실제 값을 입력하세요")
            }
        } else {
            Fail $key '키가 없음'
            $score.fail++
            [void]$hints.Add("backend\.env 에 $key= 줄을 추가하세요")
        }
    }
    foreach ($key in @('OPENAI_API_KEY')) {
        if ($envContent -match "(?m)^$key\s*=\s*(.+)") {
            $val = $matches[1].Trim().Trim('"').Trim("'")
            if ($val -and $val.Length -ge 8 -and $val -notmatch '^(your-|sk-xxx)') {
                Pass $key "설정됨 (길이 $($val.Length))"
                $score.pass++
            } else {
                Warn $key "값 없음 (선택 - GPT 분류 비활성)"
                $score.warn++
            }
        } else {
            Warn $key '키 없음 (선택)'
            $score.warn++
        }
    }
}

# ============================================================
# 7. DB 직접 쿼리: articles / users 카운트
# ============================================================
Write-Host ''
Write-Host '[7] DB 데이터 확인 (articles / users)'
Write-Host '--------------------------------------------------------------'

if ($pgPort) {
    # docker exec 로 직접 SELECT
    $pgContainer = (& docker ps --filter 'name=news_curator_db' --format '{{.Names}}' 2>&1) | Select-Object -First 1
    if (-not $pgContainer) {
        $pgContainer = (& docker ps --filter 'ancestor=pgvector/pgvector:pg16' --format '{{.Names}}' 2>&1) | Select-Object -First 1
    }
    if ($pgContainer) {
        $artCount = & docker exec $pgContainer psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM articles' 2>&1
        if ($LASTEXITCODE -eq 0 -and $artCount -match '^\d+$') {
            $n = [int]$artCount
            if ($n -gt 0) {
                Pass 'articles 테이블' "$n 건"
                $score.pass++
            } else {
                Warn 'articles 테이블' '0 건 - 크롤링이 아직 완료되지 않음 또는 실패'
                $score.warn++
                [void]$hints.Add('백엔드 cmd 창에서 "[Pipeline]" 로그 확인. NAVER API 키 / Ollama 가 정상이면 1~2분 내 기사 적재됨')
            }
        } else {
            Warn 'articles 테이블' "쿼리 실패: $artCount"
            $score.warn++
        }

        $userCount = & docker exec $pgContainer psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM users' 2>&1
        if ($LASTEXITCODE -eq 0 -and $userCount -match '^\d+$') {
            $n = [int]$userCount
            if ($n -gt 0) {
                Info 'users 테이블' "$n 명 가입"
            } else {
                Info 'users 테이블' '0 명 - 아직 회원가입 안 됨 (브라우저 /signup 으로 가입)'
            }
        }
    } else {
        Warn 'DB 직접 쿼리' 'postgres 컨테이너 이름을 찾을 수 없음 - 수동 확인 필요'
        $score.warn++
    }
} else {
    Info 'DB 직접 쿼리' 'postgres 가 떠 있지 않아 건너뜀'
}

# ============================================================
# 요약
# ============================================================
Write-Host ''
Write-Host '=============================================================='
Write-Host '  진단 요약'
Write-Host '=============================================================='
Write-Host ("  PASS: {0}    WARN: {1}    FAIL: {2}" -f $score.pass, $score.warn, $score.fail) -ForegroundColor White

if ($hints.Count -gt 0) {
    Write-Host ''
    Write-Host '  >> 권장 조치:' -ForegroundColor Yellow
    $i = 1
    foreach ($h in $hints) {
        Write-Host ("     {0}. {1}" -f $i, $h)
        $i++
    }
}

Write-Host ''
if ($score.fail -eq 0) {
    Write-Host '  >> 모든 핵심 항목 통과. 브라우저에서 http://localhost:5173 접속 후' -ForegroundColor Green
    Write-Host '     로그인했는데도 피드가 비어 있다면 articles 가 아직 0건일 가능성이 큽니다.' -ForegroundColor Green
    Write-Host '     1~2분 대기 후 페이지 새로고침하세요.' -ForegroundColor Green
} else {
    Write-Host '  >> FAIL 항목을 위 권장 조치대로 해결한 뒤 .\run_all.bat 를 다시 실행하세요.' -ForegroundColor Red
}
Write-Host '=============================================================='
Write-Host ''
