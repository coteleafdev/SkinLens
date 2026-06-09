# 배포용 ZIP 패키지 생성 스크립트 (PowerShell)
# 민감 정보 파일을 제외하고 ZIP 생성

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ZipName = "skinlens_v1.0_$Timestamp.zip"
$OutputDir = Join-Path $ProjectRoot "release"

Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "SkinLens v1.0 배포 패키지 생성" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "프로젝트 루트: $ProjectRoot"
Write-Host "ZIP 파일명: $ZipName"
Write-Host ""

# 출력 디렉토리 생성
if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir | Out-Null
}

# 제외할 파일/디렉토리 목록
$ExcludePatterns = @(
    "config\config.secrets.json"
    "*.secrets.json"
    ".env"
    ".env.*"
    "**\__pycache__\**"
    "*.pyc"
    "*.db"
    "*.xlsx"
    "data\db\"
    "logs\"
    "temp\"
    "backup\"
    "results\"
    ".pytest_cache\"
    "models\"
    "RestoreFormerPlusPlus\weights\"
    "CodeFormer\weights\"
    "*.ckpt"
    "*.pth"
    "*.egg-info\"
    "dist\"
    "build\"
    ".venv\"
)

Write-Host "ZIP 생성 중..." -ForegroundColor Yellow

# PowerShell 5.1+ Compress-Archive 사용
$TempDir = Join-Path $env:TEMP "ai_skin_deploy_$Timestamp"
New-Item -ItemType Directory -Path $TempDir | Out-Null

try {
    # 제외 패턴을 제외하고 파일 복사
    Get-ChildItem -Path $ProjectRoot -Recurse | ForEach-Object {
        $ShouldExclude = $false
        foreach ($Pattern in $ExcludePatterns) {
            if ($_.FullName -like $Pattern) {
                $ShouldExclude = $true
                break
            }
        }
        
        if (-not $ShouldExclude) {
            # 상대 경로 유지
            $RelativePath = $_.FullName.Substring($ProjectRoot.Length + 1)
            $DestPath = Join-Path $TempDir $RelativePath
            
            if ($_.PSIsContainer) {
                if (-not (Test-Path $DestPath)) {
                    New-Item -ItemType Directory -Path $DestPath | Out-Null
                }
            } else {
                $DestDir = Split-Path -Parent $DestPath
                if (-not (Test-Path $DestDir)) {
                    New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
                }
                Copy-Item -Path $_.FullName -Destination $DestPath -Force
            }
        }
    }
    
    # ZIP 생성
    $ZipPath = Join-Path $OutputDir $ZipName
    Compress-Archive -Path "$TempDir\*" -DestinationPath $ZipPath -Force
    
    $ZipSize = (Get-Item $ZipPath).Length / 1MB
    Write-Host ""
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "배포 패키지 생성 완료" -ForegroundColor Green
    Write-Host "=========================================" -ForegroundColor Green
    Write-Host "위치: $ZipPath"
    Write-Host "크기: $([math]::Round($ZipSize, 2)) MB"
    Write-Host ""
    Write-Host "제외된 파일:" -ForegroundColor Yellow
    Write-Host "  - config\config.secrets.json (민감 정보)"
    Write-Host "  - *.secrets.json (민감 정보)"
    Write-Host "  - .env, .env.* (환경 변수)"
    Write-Host "  - 모델 가중치 파일 (용량)"
    Write-Host "  - 런타임 생성 파일"
    Write-Host ""
}
finally {
    # 임시 디렉토리 정리
    if (Test-Path $TempDir) {
        Remove-Item -Path $TempDir -Recurse -Force
    }
}
