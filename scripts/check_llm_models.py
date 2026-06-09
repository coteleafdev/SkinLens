"""
LLM API에서 사용 가능한 모델 목록을 확인하는 스크립트
"""
import sys
from pathlib import Path

try:
    import google.generativeai as genai
except ImportError:
    print("google-generativeai 패키지가 설치되지 않았습니다.")
    print("설치 명령: pip install google-generativeai")
    sys.exit(1)


def _load_llm_api_key() -> str:
    """config/secrets.json에서 LLM API key를 로드합니다."""
    # 프로젝트 루트 기준 경로 탐색
    script_dir = Path(__file__).resolve().parent.parent  # 프로젝트 루트로 이동
    candidates = [
        script_dir / "config" / "config.secrets.json",
        script_dir / "config" / "secrets.json",
    ]
    
    secrets_path = None
    for cand in candidates:
        if cand.is_file():
            secrets_path = cand
            break
    
    if secrets_path is None:
        raise FileNotFoundError(
            f"secrets 파일을 찾을 수 없습니다. 다음 경로들을 확인하세요:\n"
            f"  - {candidates[0]}\n"
            f"  - {candidates[1]}"
        )
    
    import json
    try:
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"secrets 파일 JSON 파싱 오류: {e}")
    
    try:
        api_key = secrets["ai_providers"]["gemini"]["api_key"]
    except KeyError:
        raise KeyError(
            f"secrets 파일에 'ai_providers.gemini.api_key' 키가 없습니다.\n"
            f"파일 경로: {secrets_path}"
        )
    
    if not api_key or not isinstance(api_key, str):
        raise ValueError(
            f"secrets 파일의 'ai_providers.gemini.api_key'가 비어있거나 문자열이 아닙니다.\n"
            f"파일 경로: {secrets_path}"
        )
    
    return api_key


def main():
    try:
        # API Key 로드
        api_key = _load_llm_api_key()
        print(f"API Key 로드 완료 (마스킹: {api_key[:10]}...{api_key[-4:]})")
        
        # API 설정
        genai.configure(api_key=api_key)
        
        # 사용 가능한 모델 목록 가져오기
        print("\n=== LLM API 사용 가능한 모델 목록 ===\n")
        
        models = genai.list_models()
        
        vision_models = []
        text_models = []
        
        for model in models:
            model_name = model.name
            display_name = model.display_name
            description = model.description
            supported_methods = ", ".join(model.supported_generation_methods)
            
            # Vision 기능 지원 여부 확인
            supports_vision = "generateContent" in model.supported_generation_methods
            
            model_info = f"\n모델: {model_name}\n"
            model_info += f"  표시 이름: {display_name}\n"
            model_info += f"  설명: {description}\n"
            model_info += f"  지원 메서드: {supported_methods}\n"
            model_info += f"  Vision 지원: {'예' if supports_vision else '아니오'}"
            
            if supports_vision:
                vision_models.append(model_info)
            else:
                text_models.append(model_info)
        
        if vision_models:
            print("=== Vision 기능 지원 모델 (이미지 분석용) ===")
            for info in vision_models:
                print(info)
        
        if text_models:
            print("\n=== 텍스트 전용 모델 ===")
            for info in text_models:
                print(info)
        
        print("\n=== 추천 모델 ===")
        print("Vision 기능이 필요한 경우 위 'Vision 기능 지원 모델' 중 하나를 사용하세요.")
        print("피부 분석 소견 생성에는 Vision 기능이 필요합니다.")
        
    except Exception as e:
        print(f"\n오류 발생: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
