# Docker Named Volume → 직접 마운트 마이그레이션 스크립트
# 사용법: .\scripts\migrate-to-local-volumes.ps1

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🔄 Docker Volume 마이그레이션" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "Named Volume → 로컬 폴더 (./data/)" -ForegroundColor Gray
Write-Host ""

# 1. Docker 중지
Write-Host "1️⃣  Docker 컨테이너 중지 중..." -ForegroundColor Yellow
docker compose down

Write-Host ""

# 2. Named Volume 존재 확인
Write-Host "2️⃣  Named Volume 확인 중..." -ForegroundColor Yellow
$volumes = docker volume ls --format "{{.Name}}" | Select-String "chatbot-ai"

if (-not $volumes) {
    Write-Host "⚠️  Named Volume이 없습니다." -ForegroundColor Yellow
    Write-Host "   이미 마이그레이션되었거나 처음 실행하는 경우입니다." -ForegroundColor Gray
    Write-Host ""
    Write-Host "✅ 바로 Docker를 시작하면 됩니다:" -ForegroundColor Green
    Write-Host "   docker compose up -d" -ForegroundColor Gray
    exit 0
}

Write-Host "   발견된 Volume:" -ForegroundColor Gray
$volumes | ForEach-Object { Write-Host "   - $_" -ForegroundColor Gray }
Write-Host ""

# 3. 데이터 마이그레이션
Write-Host "3️⃣  데이터 마이그레이션 중..." -ForegroundColor Yellow

# data 디렉토리 생성
New-Item -ItemType Directory -Path ".\data" -Force | Out-Null
New-Item -ItemType Directory -Path ".\data\mongodb" -Force | Out-Null
New-Item -ItemType Directory -Path ".\data\mongodb-config" -Force | Out-Null
New-Item -ItemType Directory -Path ".\data\redis" -Force | Out-Null

# MongoDB 데이터 복사
Write-Host "   📦 MongoDB 데이터 복사 중..." -ForegroundColor Green
$mongoVolume = docker volume ls --format "{{.Name}}" | Select-String "mongodb_data"
if ($mongoVolume) {
    docker run --rm `
        -v ${mongoVolume}:/from `
        -v ${PWD}/data/mongodb:/to `
        alpine sh -c "cp -av /from/. /to/"
    Write-Host "   ✅ MongoDB 데이터 복사 완료" -ForegroundColor Green
}

# Redis 데이터 복사
Write-Host "   📦 Redis 데이터 복사 중..." -ForegroundColor Green
$redisVolume = docker volume ls --format "{{.Name}}" | Select-String "redis_data"
if ($redisVolume) {
    docker run --rm `
        -v ${redisVolume}:/from `
        -v ${PWD}/data/redis:/to `
        alpine sh -c "cp -av /from/. /to/"
    Write-Host "   ✅ Redis 데이터 복사 완료" -ForegroundColor Green
}

Write-Host ""

# 4. 데이터 크기 확인
Write-Host "4️⃣  마이그레이션된 데이터 확인..." -ForegroundColor Yellow
$mongoSize = (Get-ChildItem ".\data\mongodb" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1GB
$redisSize = (Get-ChildItem ".\data\redis" -Recurse -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum / 1MB

Write-Host "   MongoDB: $([math]::Round($mongoSize, 2)) GB" -ForegroundColor Gray
Write-Host "   Redis: $([math]::Round($redisSize, 2)) MB" -ForegroundColor Gray
Write-Host ""

# 5. Named Volume 삭제 확인
Write-Host "5️⃣  Named Volume 정리..." -ForegroundColor Yellow
Write-Host "   ⚠️  기존 Named Volume을 삭제할까요?" -ForegroundColor Yellow
Write-Host "   (데이터는 이미 ./data/로 복사되었습니다)" -ForegroundColor Gray
$confirmation = Read-Host "   삭제하시겠습니까? (yes/no)"

if ($confirmation -eq "yes") {
    $volumes | ForEach-Object {
        Write-Host "   🗑️  삭제: $_" -ForegroundColor Gray
        docker volume rm $_ 2>$null
    }
    Write-Host "   ✅ Named Volume 삭제 완료" -ForegroundColor Green
} else {
    Write-Host "   ℹ️  Named Volume 유지됨 (필요 시 수동 삭제 가능)" -ForegroundColor Gray
    Write-Host "      docker volume rm chatbot-ai_mongodb_data chatbot-ai_redis_data" -ForegroundColor Gray
}

Write-Host ""

# 6. Docker 재시작
Write-Host "6️⃣  Docker 재시작 중..." -ForegroundColor Yellow
docker compose up -d

Write-Host ""

# 7. 완료
Write-Host "=========================================" -ForegroundColor Green
Write-Host "✅ 마이그레이션 완료!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host ""
Write-Host "📁 데이터 위치: .\data\" -ForegroundColor Gray
Write-Host "   - .\data\mongodb\" -ForegroundColor Gray
Write-Host "   - .\data\mongodb-config\" -ForegroundColor Gray
Write-Host "   - .\data\redis\" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 이제 가능한 작업:" -ForegroundColor Yellow
Write-Host "   1. 백업: .\scripts\backup-data-windows.ps1" -ForegroundColor Gray
Write-Host "   2. 크롤링: docker exec -it knu-chatbot-app python src/modules/run_crawler.py" -ForegroundColor Gray
Write-Host "   3. EC2 전송: rsync -avz .\data\ ubuntu@ec2:/opt/knu-chatbot/CHATBOT-AI/data/" -ForegroundColor Gray
Write-Host ""
Write-Host "📊 컨테이너 상태 확인:" -ForegroundColor Yellow
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
Write-Host ""
