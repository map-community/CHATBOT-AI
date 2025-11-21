# Windows PowerShell 크롤링 스크립트
# 사용법: .\scripts\crawl-with-backup.ps1

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🚀 안전 크롤링 시작 (Windows)" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "1. 데이터 백업"
Write-Host "2. 크롤링 실행"
Write-Host "3. 성공/실패 처리"
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# Docker 실행 확인
Write-Host "🔍 Docker 상태 확인 중..." -ForegroundColor Yellow
$dockerRunning = docker ps --format "{{.Names}}" | Select-String "knu-chatbot-app"

if (-not $dockerRunning) {
    Write-Host "⚠️  Docker 컨테이너가 실행 중이 아닙니다." -ForegroundColor Yellow
    Write-Host "🚀 Docker 시작 중..." -ForegroundColor Green

    if (Test-Path "docker-compose.prod.yml") {
        docker compose -f docker-compose.prod.yml up -d
    } else {
        docker compose up -d
    }

    Write-Host "⏳ 컨테이너 초기화 대기 중... (30초)" -ForegroundColor Yellow
    Start-Sleep -Seconds 30
}

# 백업 실행
Write-Host ""
Write-Host "📍 1단계: 데이터 백업" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupName = "data-backup-$timestamp"

Write-Host "💾 Docker 컨테이너 내부에서 백업 실행 중..." -ForegroundColor Green
docker exec -it knu-chatbot-app bash -c "cd /app && ./scripts/backup-data.sh"

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan

# 크롤링 실행
Write-Host "📍 2단계: 크롤링 실행" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

$crawlSuccess = $false

try {
    docker exec -it knu-chatbot-app python src/modules/run_crawler.py
    $crawlSuccess = $true

    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "✅ 크롤링 성공!" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
} catch {
    $crawlSuccess = $false

    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Red
    Write-Host "❌ 크롤링 실패!" -ForegroundColor Red
    Write-Host "=========================================" -ForegroundColor Red
}

Write-Host ""

# 성공/실패 처리
if ($crawlSuccess) {
    Write-Host "📍 3단계: 성공 처리" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "✅ 백업 유지됨: $backupName" -ForegroundColor Green
    Write-Host "   (필요시 복원 가능)" -ForegroundColor Gray
    Write-Host ""
    Write-Host "💡 백업에서 복원하려면:" -ForegroundColor Yellow
    Write-Host "   docker exec -it knu-chatbot-app bash -c `"cd /app && ./scripts/restore-data.sh $backupName`"" -ForegroundColor Gray
    Write-Host ""
} else {
    Write-Host "📍 3단계: 실패 처리" -ForegroundColor Cyan
    Write-Host "=========================================" -ForegroundColor Cyan
    Write-Host "❌ 크롤링이 실패했습니다." -ForegroundColor Red
    Write-Host ""
    Write-Host "⚠️  중요: Pinecone-MongoDB 불일치 위험!" -ForegroundColor Yellow
    Write-Host "   크롤링 중 Pinecone에 벡터가 업로드되었을 수 있습니다." -ForegroundColor Yellow
    Write-Host "   MongoDB만 복원하면 Pinecone과 불일치 발생!" -ForegroundColor Yellow
    Write-Host ""

    $response = Read-Host "백업에서 복원하시겠습니까? (yes/no)"

    if ($response -eq "yes") {
        Write-Host ""
        Write-Host "♻️  백업에서 복원 중..." -ForegroundColor Green
        docker exec -it knu-chatbot-app bash -c "cd /app && ./scripts/restore-data.sh $backupName"

        Write-Host ""
        Write-Host "🧹 Pinecone 정리 안내..." -ForegroundColor Yellow
        Write-Host ""
        Write-Host "💡 Pinecone 동기화 확인 필요:" -ForegroundColor Yellow
        Write-Host "   1. 테스트 질문 실행" -ForegroundColor Gray
        Write-Host "   2. '문서를 찾을 수 없습니다' 에러 발생 시:" -ForegroundColor Gray
        Write-Host "      → docker exec -it knu-chatbot-app python scripts/cleanup-pinecone-sync.py --dry-run" -ForegroundColor Gray
        Write-Host "      → docker exec -it knu-chatbot-app python scripts/cleanup-pinecone-sync.py" -ForegroundColor Gray
        Write-Host ""

        Write-Host "🚀 Docker 재시작 중..." -ForegroundColor Green
        if (Test-Path "docker-compose.prod.yml") {
            docker compose -f docker-compose.prod.yml down
            docker compose -f docker-compose.prod.yml up -d
        } else {
            docker compose down
            docker compose up -d
        }

        Write-Host ""
        Write-Host "=========================================" -ForegroundColor Green
        Write-Host "✅ MongoDB 복원 완료!" -ForegroundColor Green
        Write-Host "=========================================" -ForegroundColor Green
    } else {
        Write-Host "⚠️  백업은 유지됩니다: $backupName" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "💡 나중에 복원하려면:" -ForegroundColor Yellow
        Write-Host "   docker exec -it knu-chatbot-app bash -c `"cd /app && ./scripts/restore-data.sh $backupName`"" -ForegroundColor Gray
    }
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🎉 작업 완료" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
