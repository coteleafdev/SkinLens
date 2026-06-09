#!/bin/bash
# 배포용 ZIP 패키지 생성 스크립트
# 민감 정보 파일을 제외하고 ZIP 생성

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ZIP_NAME="skinlens_v1.0_$(date +%Y%m%d_%H%M%S).zip"
OUTPUT_DIR="$PROJECT_ROOT/release"

echo "========================================="
echo "SkinLens v1.0 배포 패키지 생성"
echo "========================================="
echo "프로젝트 루트: $PROJECT_ROOT"
echo "ZIP 파일명: $ZIP_NAME"
echo ""

# 출력 디렉토리 생성
mkdir -p "$OUTPUT_DIR"

# ZIP 생성 (민감 정보 제외)
echo "ZIP 생성 중..."
cd "$PROJECT_ROOT"
zip -r "$OUTPUT_DIR/$ZIP_NAME" . \
  --exclude "config/config.secrets.json" \
  --exclude "*.secrets.json" \
  --exclude ".env" \
  --exclude ".env.*" \
  --exclude "**/__pycache__/**" \
  --exclude "*.pyc" \
  --exclude "*.db" \
  --exclude "*.xlsx" \
  --exclude "data/db/" \
  --exclude "logs/" \
  --exclude "temp/" \
  --exclude "backup/" \
  --exclude "results/" \
  --exclude ".pytest_cache/" \
  --exclude "models/" \
  --exclude "RestoreFormerPlusPlus/weights/" \
  --exclude "CodeFormer/weights/" \
  --exclude "*.ckpt" \
  --exclude "*.pth" \
  --exclude "*.egg-info/" \
  --exclude "dist/" \
  --exclude "build/" \
  --exclude ".venv/"

echo ""
echo "========================================="
echo "배포 패키지 생성 완료"
echo "========================================="
echo "위치: $OUTPUT_DIR/$ZIP_NAME"
echo "크기: $(du -h "$OUTPUT_DIR/$ZIP_NAME" | cut -f1)"
echo ""
echo "제외된 파일:"
echo "  - config/config.secrets.json (민감 정보)"
echo "  - *.secrets.json (민감 정보)"
echo "  - .env, .env.* (환경 변수)"
echo "  - models/ (외부 모델)"
echo "  - data/db/, logs/, temp/, backup/ (런타임 생성)"
echo "  - 모델 가중치 파일 (용량)"
echo ""
