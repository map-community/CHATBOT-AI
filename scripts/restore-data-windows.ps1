# Windows PowerShell 데이터 복원 스크립트
# 사용법: .\scripts\restore-data-windows.ps1 <백업명>
# 예시: .\scripts\restore-data-windows.ps1 data-backup-20251121_120000

param(
    [Parameter(Mandatory=$false)]
    [string]$BackupName
)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "♻️  데이터 복원 시작" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 백업 이름 확인
if (-not $BackupName) {
    Write-Host "❌ 사용법: .\scripts\restore-data-windows.ps1 <백업명>" -ForegroundColor Red
    Write-Host ""
    Write-Host "사용 가능한 백업 목록:" -ForegroundColor Yellow

    if (Test-Path ".\data-backups") {
        Get-ChildItem ".\data-backups" -Directory |
            Where-Object { $_.Name -match "^data-backup-" } |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object {
                $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
                $sizeFormatted = "{0:N2} GB" -f $size
                Write-Host "  $($_.Name) - $sizeFormatted" -ForegroundColor Gray
            }
    } else {
        Write-Host "  백업이 없습니다." -ForegroundColor Gray
    }

    Write-Host ""
    Write-Host "예시:" -ForegroundColor Yellow
    Write-Host "  .\scripts\restore-data-windows.ps1 data-backup-20251121_120000" -ForegroundColor Gray
    exit 1
}

$backupPath = ".\data-backups\$BackupName"

Write-Host "복원할 백업: $BackupName" -ForegroundColor Gray
Write-Host "백업 경로: $backupPath" -ForegroundColor Gray
Write-Host ""

# 백업 존재 확인
if (-not (Test-Path $backupPath)) {
    Write-Host "❌ 백업을 찾을 수 없습니다: $backupPath" -ForegroundColor Red
    Write-Host ""
    Write-Host "사용 가능한 백업 목록:" -ForegroundColor Yellow

    if (Test-Path ".\data-backups") {
        Get-ChildItem ".\data-backups" -Directory |
            Where-Object { $_.Name -match "^data-backup-" } |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object { Write-Host "  $($_.Name)" -ForegroundColor Gray }
    } else {
        Write-Host "  백업이 없습니다." -ForegroundColor Gray
    }

    exit 1
}

# 확인 메시지
Write-Host "⚠️  경고: 현재 데이터가 백업으로 대체됩니다!" -ForegroundColor Yellow
Write-Host ""
$confirmation = Read-Host "계속하시겠습니까? (yes/no)"

if ($confirmation -ne "yes") {
    Write-Host "❌ 복원이 취소되었습니다." -ForegroundColor Red
    exit 0
}

Write-Host ""

# Docker 중지 확인
$dockerRunning = docker ps --format "{{.Names}}" 2>$null | Select-String "knu-chatbot"

if ($dockerRunning) {
    Write-Host "🛑 Docker 컨테이너를 먼저 중지해야 합니다." -ForegroundColor Yellow
    $stopDocker = Read-Host "Docker를 중지하시겠습니까? (yes/no)"

    if ($stopDocker -eq "yes") {
        Write-Host "🛑 Docker 중지 중..." -ForegroundColor Yellow

        if (Test-Path "docker-compose.prod.yml") {
            docker compose -f docker-compose.prod.yml down 2>$null
        } else {
            docker compose down 2>$null
        }
    } else {
        Write-Host "❌ Docker를 먼저 중지해주세요:" -ForegroundColor Red
        Write-Host "   docker compose down" -ForegroundColor Gray
        exit 1
    }
}

# 현재 데이터 임시 백업 (안전장치)
if (Test-Path ".\data") {
    $tempBackup = "data.before-restore-$(Get-Date -Format 'yyyyMMdd_HHmmss')"
    Write-Host "💾 현재 데이터 임시 백업 중: $tempBackup" -ForegroundColor Yellow
    Move-Item ".\data" $tempBackup -Force
    Write-Host "   (복원 실패 시 여기서 복구 가능)" -ForegroundColor Gray
    Write-Host ""
}

# 백업에서 복원
Write-Host "📦 백업에서 데이터 복원 중..." -ForegroundColor Green
try {
    Copy-Item -Path $backupPath -Destination ".\data" -Recurse -Force

    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "✅ 복원 완료!" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "복원된 백업: $BackupName" -ForegroundColor Gray
    Write-Host ""
    Write-Host "💡 다음 단계:" -ForegroundColor Yellow
    Write-Host "   1. Docker 시작: docker compose up -d" -ForegroundColor Gray
    Write-Host "   2. 로그 확인: docker logs -f knu-chatbot-app" -ForegroundColor Gray
    Write-Host ""
    Write-Host "💡 임시 백업 위치 (문제 발생 시 복구용):" -ForegroundColor Yellow
    Write-Host "   $tempBackup" -ForegroundColor Gray
    Write-Host ""

} catch {
    Write-Host ""
    Write-Host "❌ 복원 실패: $($_.Exception.Message)" -ForegroundColor Red

    # 실패 시 임시 백업에서 복구
    if (Test-Path $tempBackup) {
        Write-Host "♻️  임시 백업에서 복구 중..." -ForegroundColor Yellow
        Move-Item $tempBackup ".\data" -Force
        Write-Host "✅ 이전 상태로 복구되었습니다." -ForegroundColor Green
    }

    exit 1
}
