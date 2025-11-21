# 로컬 MongoDB 데이터를 EC2로 안전하게 동기화 (Windows PowerShell)
# 사용법: .\scripts\sync-to-ec2.ps1

param(
    [string]$EC2Key = "C:\Users\Park\knu-chatbot-key.pem",
    [string]$EC2User = "ubuntu",
    [string]$EC2Host = "3.39.153.45",
    [string]$EC2Path = "/opt/knu-chatbot/CHATBOT-AI"
)

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "🚀 로컬 → EC2 데이터 동기화" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "방법: mongodump (안전, 서비스 중단 없음)" -ForegroundColor Gray
Write-Host ""

# SSH 키 확인
if (-not (Test-Path $EC2Key)) {
    Write-Host "❌ SSH 키를 찾을 수 없습니다: $EC2Key" -ForegroundColor Red
    exit 1
}

# 1. 로컬에서 MongoDB 덤프
Write-Host "1️⃣  로컬 MongoDB 덤프 생성 중..." -ForegroundColor Yellow
docker exec knu-chatbot-mongodb mongodump --out=/dump --db=knu_chatbot

# 2. 덤프 파일을 Windows로 복사
Write-Host "2️⃣  덤프 파일 추출 중..." -ForegroundColor Yellow
if (Test-Path ".\mongo-dump-temp") {
    Remove-Item ".\mongo-dump-temp" -Recurse -Force
}
docker cp knu-chatbot-mongodb:/dump .\mongo-dump-temp

# 3. scp로 EC2로 전송 (PowerShell에서는 scp 사용)
Write-Host "3️⃣  EC2로 전송 중..." -ForegroundColor Yellow
Write-Host "   (Git Bash가 설치되어 있다면 rsync가 더 빠릅니다)" -ForegroundColor Gray

# Git Bash 경로 찾기
$gitBashPath = "C:\Program Files\Git\bin\bash.exe"

if (Test-Path $gitBashPath) {
    # Git Bash 있으면 rsync 사용 (더 빠름)
    Write-Host "   Git Bash 발견 - rsync 사용" -ForegroundColor Green

    & $gitBashPath -c @"
        rsync -avz --progress \
          -e 'ssh -i /c/Users/Park/knu-chatbot-key.pem' \
          ./mongo-dump-temp/ \
          $EC2User@${EC2Host}:/tmp/mongo-dump/
"@
} else {
    # Git Bash 없으면 scp 사용
    Write-Host "   scp 사용 (rsync보다 느릴 수 있음)" -ForegroundColor Yellow
    scp -i $EC2Key -r .\mongo-dump-temp\* ${EC2User}@${EC2Host}:/tmp/mongo-dump/
}

# 4. EC2에서 복원
Write-Host "4️⃣  EC2에서 복원 중..." -ForegroundColor Yellow

$sshCommand = @"
cd $EC2Path
docker cp /tmp/mongo-dump knu-chatbot-mongodb:/dump
docker exec knu-chatbot-mongodb mongorestore --db=knu_chatbot /dump/knu_chatbot --drop
rm -rf /tmp/mongo-dump
echo '✅ EC2 복원 완료!'
"@

ssh -i $EC2Key ${EC2User}@${EC2Host} $sshCommand

# 5. 로컬 임시 파일 정리
Write-Host "5️⃣  로컬 임시 파일 정리 중..." -ForegroundColor Yellow
Remove-Item ".\mongo-dump-temp" -Recurse -Force

Write-Host ""
Write-Host "=========================================" -ForegroundColor Green
Write-Host "✅ 동기화 완료!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Green
Write-Host "EC2 주소: http://$EC2Host:5000" -ForegroundColor Gray
Write-Host ""
Write-Host "💡 확인 방법:" -ForegroundColor Yellow
Write-Host "   ssh -i $EC2Key ${EC2User}@${EC2Host}" -ForegroundColor Gray
Write-Host "   docker logs -f knu-chatbot-app" -ForegroundColor Gray
Write-Host ""
