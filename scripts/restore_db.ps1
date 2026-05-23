# ============================================================
#  News Curator - DB 복원 스크립트 (restore_db.ps1)
# ------------------------------------------------------------
#  backup_db.ps1 로 만든 .dump 파일을 새 머신의
#  news_curator DB 에 복원한다.
#
#  사용:
#    .\restore_db.bat                          # backups\ 의 최신 파일 자동 선택
#    .\restore_db.bat path\to\foo.dump          # 특정 파일 지정
# ============================================================

param([string]$DumpFile = '')

$ErrorActionPreference = 'Stop'
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false) } catch {}
try { chcp 65001 > $null } catch {}

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $ROOT

Write-Host ''
Write-Host '=============================================================='
Write-Host '  News Curator - DB 복원 (restore_db.ps1)'
Write-Host '=============================================================='

# --- 1. 덤프 파일 결정 ---
if (-not $DumpFile) {
    $backupDir = Join-Path $ROOT 'backups'
    if (-not (Test-Path $backupDir)) {
        Write-Host "[오류] backups\ 디렉터리가 없습니다." -ForegroundColor Red
        Write-Host '       복원할 .dump 파일을 backups\ 폴더에 두거나, 파일 경로를 인자로 전달하세요:'
        Write-Host '       powershell -File scripts\restore_db.ps1 C:\path\to\foo.dump'
        exit 1
    }
    $latest = Get-ChildItem -Path $backupDir -Filter '*.dump' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        Write-Host "[오류] backups\ 안에 .dump 파일이 없습니다." -ForegroundColor Red
        exit 1
    }
    $DumpFile = $latest.FullName
    Write-Host "  자동 선택: $($latest.Name) ($([math]::Round($latest.Length / 1MB, 2)) MB)"
} else {
    if (-not (Test-Path $DumpFile)) {
        Write-Host "[오류] 파일이 없습니다: $DumpFile" -ForegroundColor Red
        exit 1
    }
}

# --- 2. postgres 컨테이너 확인 ---
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

# --- 3. 기존 데이터 경고 ---
$existingArticles = & docker exec $container psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM articles' 2>$null
if ($LASTEXITCODE -eq 0 -and $existingArticles -match '^\d+$' -and [int]$existingArticles -gt 0) {
    Write-Host ''
    Write-Host "  ⚠ 현재 DB 에 articles $existingArticles 건이 이미 있습니다." -ForegroundColor Yellow
    Write-Host '    복원은 기존 데이터를 모두 삭제하고 덤프로 교체합니다.'
    $cont = Read-Host '계속하시겠습니까? [y/N]'
    if ($cont -notmatch '^(y|Y)$') {
        Write-Host '  취소됨.'
        exit 0
    }
}

# --- 4. 컨테이너로 파일 복사 ---
$containerPath = '/tmp/restore_input.dump'
Write-Host ''
Write-Host '  덤프 파일을 컨테이너로 복사 중...'
& docker cp $DumpFile "${container}:${containerPath}"
if ($LASTEXITCODE -ne 0) { Write-Host '[오류] docker cp 실패' -ForegroundColor Red; exit 1 }

# --- 5. pg_restore 실행 ---
Write-Host '  pg_restore 실행 중... (수 초~수 분 소요)'
# --clean --if-exists: 기존 객체 제거 후 새로 만듦 / 없어도 에러 안 남
# --no-owner: 다른 머신의 사용자 차이 무시
& docker exec $container pg_restore -U postgres -d news_curator --clean --if-exists --no-owner --no-privileges $containerPath
$restoreExit = $LASTEXITCODE

# 임시파일 정리
& docker exec $container rm $containerPath 2>$null | Out-Null

# pg_restore 는 일부 객체 충돌 시에도 0 이 아닌 코드를 낼 수 있음 (실제 데이터는 정상 복원)
# 그래서 결과는 row count 로 검증
$newArticles = & docker exec $container psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM articles' 2>$null
$newUsers = & docker exec $container psql -U postgres -d news_curator -tAc 'SELECT COUNT(*) FROM users' 2>$null

Write-Host ''
Write-Host '=============================================================='
if ($newArticles -match '^\d+$' -and [int]$newArticles -gt 0) {
    Write-Host '  복원 완료' -ForegroundColor Green
    Write-Host '--------------------------------------------------------------'
    Write-Host "  articles : $newArticles 건"
    Write-Host "  users    : $newUsers 명"
} else {
    Write-Host '  복원 실패 가능성 - articles 가 0건입니다' -ForegroundColor Red
    Write-Host "  pg_restore 종료 코드: $restoreExit"
    Write-Host '  docker logs news_curator_db 로 원인을 확인하세요.'
}
Write-Host '=============================================================='
Write-Host ''
Write-Host '  주의: backend\.env 도 옮겨왔어야 SECRET_KEY 가 동일하여'
Write-Host '        기존 사용자 JWT 토큰이 새 머신에서도 인증됩니다.'
Write-Host '        다르면 사용자가 재로그인 한 번 해야 합니다.'
Write-Host '=============================================================='
exit 0
