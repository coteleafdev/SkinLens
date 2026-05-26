"""
i18n.py — 다국어 미들웨어

기능:
- 요청 언어 감지 (Accept-Language 헤더, 쿼리 파라미터)
- 번역 적용
- 언어 컨텍스트 설정
"""
import logging
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from src.i18n import Translator, translate

log = logging.getLogger(__name__)


class I18nMiddleware(BaseHTTPMiddleware):
    """다국어 미들웨어"""
    
    def __init__(self, app, translator: Optional[Translator] = None):
        super().__init__(app)
        self.translator = translator or Translator()
    
    async def dispatch(self, request: Request, call_next):
        # 언어 감지
        language = self._detect_language(request)
        
        # 언어를 request state에 저장
        request.state.language = language
        
        # 요청 처리
        response = await call_next(request)
        
        # JSON 응답인 경우 번역 적용
        if isinstance(response, JSONResponse):
            response = self._translate_response(response, language)
        
        return response
    
    def _detect_language(self, request: Request) -> str:
        """언어 감지"""
        # 1. 쿼리 파라미터 우선
        lang = request.query_params.get("lang")
        if lang and self.translator.is_language_supported(lang):
            return lang
        
        # 2. Accept-Language 헤더
        accept_language = request.headers.get("accept-language", "")
        if accept_language:
            # Accept-Language 파싱 (예: "ko-KR,ko;q=0.9,en;q=0.8")
            languages = [lang.split(";")[0].strip() for lang in accept_language.split(",")]
            for lang in languages:
                # 언어 코드 추출 (예: "ko-KR" -> "ko")
                lang_code = lang.split("-")[0].lower()
                if self.translator.is_language_supported(lang_code):
                    return lang_code
        
        # 3. 기본 언어
        return Translator.DEFAULT_LANGUAGE
    
    def _translate_response(self, response: JSONResponse, language: str) -> JSONResponse:
        """응답 번역"""
        try:
            body = response.body.decode("utf-8")
            import json
            data = json.loads(body)
            
            # 응답 데이터 번역
            translated_data = self.translator.translate_dict(data, language)
            
            return JSONResponse(
                content=translated_data,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        except Exception as e:
            log.error(f"[I18n] 응답 번역 실패: {e}")
            return response
