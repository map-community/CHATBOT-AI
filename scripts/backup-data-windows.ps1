# Windows PowerShell 데이터 백업 스크립트
# 사용법: .\scripts\backup-data-windows.ps1

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "💾 데이터 백업 시작" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

# 타임스탬프 생성
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupName = "data-backup-$timestamp"
$backupPath = ".\data-backups\$backupName"

Write-Host "타임스탬프: $timestamp" -ForegroundColor Gray
Write-Host "백업 경로: $backupPath" -ForegroundColor Gray
Write-Host ""

# data 디렉토리 존재 확인
if (-not (Test-Path ".\data")) {
    Write-Host "❌ 데이터 디렉토리가 없습니다: .\data" -ForegroundColor Red
    exit 1
}

# data-backups 디렉토리 생성
if (-not (Test-Path ".\data-backups")) {
    Write-Host "📁 data-backups 디렉토리 생성 중..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path ".\data-backups" | Out-Null
}

# 데이터 복사
Write-Host "📦 데이터 복사 중..." -ForegroundColor Green
try {
    Copy-Item -Path ".\data" -Destination $backupPath -Recurse -Force

    # 백업 크기 계산
    $backupSize = (Get-ChildItem $backupPath -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
    $backupSizeFormatted = "{0:N2} GB" -f $backupSize

    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "✅ 백업 완료!" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "백업 위치: $backupPath" -ForegroundColor Gray
    Write-Host "백업 크기: $backupSizeFormatted" -ForegroundColor Gray
    Write-Host ""

    # 오래된 백업 정리 (7일 이상)
    Write-Host "🧹 오래된 백업 정리 중... (7일 이상)" -ForegroundColor Yellow
    $cutoffDate = (Get-Date).AddDays(-7)
    $oldBackups = Get-ChildItem ".\data-backups" -Directory | Where-Object { $_.Name -match "^data-backup-" -and $_.LastWriteTime -lt $cutoffDate }

    foreach ($oldBackup in $oldBackups) {
        Write-Host "   삭제: $($oldBackup.Name)" -ForegroundColor Gray
        Remove-Item $oldBackup.FullName -Recurse -Force
    }

    # 현재 백업 목록 출력
    Write-Host ""
    Write-Host "📋 현재 백업 목록:" -ForegroundColor Cyan
    Get-ChildItem ".\data-backups" -Directory |
        Where-Object { $_.Name -match "^data-backup-" } |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 5 |
        ForEach-Object {
            $size = (Get-ChildItem $_.FullName -Recurse | Measure-Object -Property Length -Sum).Sum / 1GB
            $sizeFormatted = "{0:N2} GB" -f $size
            Write-Host "   $($_.Name) - $sizeFormatted" -ForegroundColor Gray
        }

    Write-Host ""
    Write-Host "💡 백업에서 복원하려면:" -ForegroundColor Yellow
    Write-Host "   .\scripts\restore-data-windows.ps1 $backupName" -ForegroundColor Gray
    Write-Host ""

} catch {
    Write-Host ""
    Write-Host "❌ 백업 실패: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
