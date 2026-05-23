# ============================================================
#  News Curator - DB 백업 스크립트 (backup_db.ps1)
# ------------------------------------------------------------
#  PostgreSQL 컨테이너의 news_curator DB 를 단일 .dump 파일로
#  덤프한다. pgvector 임베딩까지 모두 포함되며, 다른 머신의
#  scripts\restore_db.ps1 로 1:1 복원 가능하다.
#
#  사용 시나리오:
#    1. 이 머신에서 .\backup_db.bat 실행
#    2. backups\news_curator_<날짜>.dump 와 backend\.env 를 USB 로 복사
#    3. 다른 머신에서 setup.bat -> run_all.bat (Docker 컨테이너 기동) 까지 한 뒤
#    4. .\restore_db.bat 실행하여 동일 데이터 복원
# ============================================================

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { chcp 65001 > $null } catch {}

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ROOT

Write-Host ''
Write-Host '=============================================================='
Write-Host '  News Curator - DB 백업 (backup_db.ps1)'
Write-Host '=============================================================='

# --- 1. postgres 컨테이너 확인 ---
$container = (& docker ps --filter 'name=news_curator_db' --format '{{.Names}}' 2>&1) | Select-Object -First 1
if (-not $container) {
    $container = (& docker ps --filter 'ancestor=pgvector/pgvector:pg16' --format '{{.Names}}' 2>&1) | Select-Object -First 1
}
if (-not $container) {
    Write-Host '[오류] PostgreSQL 컨테이너가 실행 중이 아닙니다.' -ForegroundColor Red
    Write-Host '       먼저 .\run_all.bat 또는 docker-compose up -d 를 실행하세요.'
    exit 1
}
Write-Host "  [OK] postgres 컨테이너: $container"

# --- 2. 백업 디렉터리 준비 ---
$backupDir = Join-Path $ROOT 'backups'
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir | Out-Null
    Write-Host "  [OK] backups\ 디렉터리 생성"
}

$timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$dumpFile = Join-Path $backupDir "news_curator_$timestamp.dump"
$containerPath = "/tmp/news_curator_$timestamp.dump"

# --- 3. pg_dump 실행 (컨테이너 내부에서) ---
Write-Host ''
Write-Host '  덤프 생성 중... (수 초~1분 소요)'
& docker exec $container pg_dump -U postgres -Fc -f $containerPath news_curator
if ($LASTEXITCODE -ne 0) {
    Write-Host '[오류] pg_dump 실패' -ForegroundColor Red
    exit 1
}

# --- 4. 컨테이너 -> 호스트 복사 ---
& docker cp "${container}:${containerPath}" $dumpFile
if ($LASTEXITCODE -ne 0) {
    Write-Host '[오류] 호스트로 복사 실패' -ForegroundColor Red
    exit 1
}

# --- 5. 컨테이너 안 임시파일 정리 ---
& docker exec $container rm $containerPath 2>$null | Out-Null

# --- 6. 통계 ---
$sizeBytes = (Get-Item $dumpFile).Length
$sizeMb = [math]::Round($sizeBytes / 1MB, 2)

# DB 통계 조회
$articles = & docker exec $container psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM articles' 2>$null
$users = & docker exec $container psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM users' 2>$null

Write-Host ''
Write-Host '=============================================================='
Write-Host '  백업 완료' -ForegroundColor Green
Write-Host '--------------------------------------------------------------'
Write-Host "  파일 : $dumpFile"
Write-Host "  크기 : $sizeMb MB"
Write-Host "  내용 : articles $articles 건  /  users $users 명"
Write-Host '=============================================================='
Write-Host ''
Write-Host '  USB 이동 시 함께 복사할 항목:'
Write-Host "     1) $dumpFile"
Write-Host "     2) backend\.env  (NAVER API 키, SECRET_KEY 등 동일하게 옮기려는 경우)"
Write-Host ''
Write-Host '  ⚠ backend\.env 에는 API 키와 SECRET_KEY 가 들어있습니다.'
Write-Host '    USB 가 분실되지 않도록 주의하세요.'
Write-Host '=============================================================='
exit 0
