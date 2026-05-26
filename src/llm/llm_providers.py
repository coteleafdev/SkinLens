"""
llm_providers.py — LLM 다중 프로바이더 지원 모듈

다양한 LLM 프로바이더(Gemini, OpenAI, Anthropic 등)를 추상화하여
통일된 인터페이스로 사용할 수 있게 합니다.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


class LLMProvider(ABC):
    """LLM 프로바이더 추상 클래스.
    
    모든 LLM 프로바이더는 이 클래스를 상속하여 구현해야 합니다.
    """
    
    def __init__(
        self,
        api_key: str,
        model_name: str,
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
    ) -> None:
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens
    
    @abstractmethod
    def configure(self) -> None:
        """API 클라이언트를 설정합니다."""
        pass
    
    @abstractmethod
    def generate_content(
        self,
        prompts: List[str],
        images: Optional[List[Any]] = None,
    ) -> str:
        """LLM에 콘텐츠 생성을 요청합니다.
        
        Args:
            prompts: 프롬프트 리스트 (system_prompt, user_prompt 등)
            images: 이미지 리스트 (Vision 모델인 경우)
        
        Returns:
            생성된 텍스트 응답
        """
        pass
    
    @abstractmethod
    def list_models(self) -> List[str]:
        """사용 가능한 모델 목록을 반환합니다."""
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini LLM 프로바이더."""
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gemini-2.5-flash",
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
    ) -> None:
        super().__init__(api_key, model_name, temperature, max_output_tokens)
        self._client = None
        self._genai = None
    
    def configure(self) -> None:
        """Gemini API 클라이언트를 설정합니다."""
        try:
            import google.generativeai as genai
            self._genai = genai
            genai.configure(api_key=self.api_key)
            self._client = genai.GenerativeModel(self.model_name)
            log.info(f"[GeminiProvider] 클라이언트 설정 완료: {self.model_name}")
        except ImportError:
            raise ImportError("google.generativeai 패키지가 설치되지 않았습니다. pip install google-generativeai")
    
    def generate_content(
        self,
        prompts: List[str],
        images: Optional[List[Any]] = None,
    ) -> str:
        """Gemini API에 콘텐츠 생성을 요청합니다.
        
        [FIX 2026-05-24] 재시도 가능한 오류(429, 500)와 재시도 불가능한 오류(401, 404) 구분.
        """
        if self._client is None:
            self.configure()
        
        if images is None:
            images = []
        
        content = prompts + images
        try:
            response = self._client.generate_content(
                content,
                generation_config=self._genai.types.GenerationConfig(
                    temperature=self.temperature,
                    max_output_tokens=self.max_output_tokens,
                ),
            )
            return response.text
        except Exception as e:
            # Google AI API 예외 분류
            error_msg = str(e).lower()
            # 재시도 불가능한 오류: 인증(401), 모델 없음(404)
            if "permission" in error_msg or "unauthorized" in error_msg or "401" in error_msg:
                raise PermissionError(f"LLM API 인증 실패: {e}") from e
            if "not found" in error_msg or "404" in error_msg:
                raise ValueError(f"LLM 모델을 찾을 수 없음: {e}") from e
            # 재시도 가능한 오류: 할당량 초과(429), 서버 오류(500)
            if "quota" in error_msg or "429" in error_msg or "rate limit" in error_msg:
                raise ConnectionError(f"LLM API 할당량 초과 (재시도 가능): {e}") from e
            if "500" in error_msg or "internal" in error_msg or "server" in error_msg:
                raise ConnectionError(f"LLM API 서버 오류 (재시도 가능): {e}") from e
            # 기타 오류는 그대로 전파
            raise
    
    def list_models(self) -> List[str]:
        """사용 가능한 Gemini 모델 목록을 반환합니다."""
        if self._genai is None:
            try:
                import google.generativeai as genai
                self._genai = genai
            except ImportError:
                return []
        
        try:
            models = self._genai.list_models()
            vision_models = [m.name for m in models if "generateContent" in m.supported_generation_methods]
            return vision_models
        except Exception as e:
            log.warning(f"[GeminiProvider] 모델 목록 조회 실패: {e}")
            return []


class OpenAIProvider(LLMProvider):
    """OpenAI LLM 프로바이더 (향후 확장용)."""
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "gpt-4o",
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
    ) -> None:
        super().__init__(api_key, model_name, temperature, max_output_tokens)
        self._client = None
    
    def configure(self) -> None:
        """OpenAI API 클라이언트를 설정합니다."""
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=self.api_key)
            log.info(f"[OpenAIProvider] 클라이언트 설정 완료: {self.model_name}")
        except ImportError:
            raise ImportError("openai 패키지가 설치되지 않았습니다. pip install openai")
    
    def generate_content(
        self,
        prompts: List[str],
        images: Optional[List[Any]] = None,
    ) -> str:
        """OpenAI API에 콘텐츠 생성을 요청합니다."""
        if self._client is None:
            self.configure()
        
        # 시스템 프롬프트와 사용자 프롬프트 분리
        system_prompt = prompts[0] if len(prompts) > 0 else ""
        user_prompt = prompts[1] if len(prompts) > 1 else ""
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        # 이미지가 있는 경우 멀티모달 메시지 구성
        if images:
            content = [{"type": "text", "text": user_prompt}]
            for img in images:
                # PIL 이미지를 base64로 변환
                import base64
                from io import BytesIO
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/png;base64,{img_str}"}
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_prompt})
        
        response = self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=self.temperature,
            max_tokens=self.max_output_tokens,
        )
        return response.choices[0].message.content
    
    def list_models(self) -> List[str]:
        """사용 가능한 OpenAI 모델 목록을 반환합니다."""
        if self._client is None:
            self.configure()
        
        try:
            models = self._client.models.list()
            return [m.id for m in models.data]
        except Exception as e:
            log.warning(f"[OpenAIProvider] 모델 목록 조회 실패: {e}")
            return []


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM 프로바이더."""
    
    def __init__(
        self,
        api_key: str,
        model_name: str = "claude-3-5-sonnet-20241022",
        temperature: float = 0.7,
        max_output_tokens: Optional[int] = None,
    ) -> None:
        super().__init__(api_key, model_name, temperature, max_output_tokens)
        self._client = None
    
    def configure(self) -> None:
        """Anthropic API 클라이언트를 설정합니다."""
        try:
            from anthropic import Anthropic
            self._client = Anthropic(api_key=self.api_key)
            log.info(f"[AnthropicProvider] 클라이언트 설정 완료: {self.model_name}")
        except ImportError:
            raise ImportError("anthropic 패키지가 설치되지 않았습니다. pip install anthropic")
    
    def generate_content(
        self,
        prompts: List[str],
        images: Optional[List[Any]] = None,
    ) -> str:
        """Anthropic API에 콘텐츠 생성을 요청합니다."""
        if self._client is None:
            self.configure()
        
        # 시스템 프롬프트와 사용자 프롬프트 분리
        system_prompt = prompts[0] if len(prompts) > 0 else ""
        user_prompt = prompts[1] if len(prompts) > 1 else ""
        
        # 이미지가 있는 경우 멀티모달 메시지 구성
        if images:
            content = [{"type": "text", "text": user_prompt}]
            for img in images:
                # PIL 이미지를 base64로 변환
                import base64
                from io import BytesIO
                buffered = BytesIO()
                img.save(buffered, format="PNG")
                img_str = base64.b64encode(buffered.getvalue()).decode()
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_str
                    }
                })
        else:
            content = user_prompt
        
        response = self._client.messages.create(
            model=self.model_name,
            max_tokens=self.max_output_tokens or 4096,
            system=system_prompt if system_prompt else None,
            messages=[{"role": "user", "content": content}],
            temperature=self.temperature,
        )
        return response.content[0].text
    
    def list_models(self) -> List[str]:
        """사용 가능한 Anthropic 모델 목록을 반환합니다.

        Note:
            Anthropic은 현재 공개 API로 모델 목록 조회를 지원하지 않아 하드코딩된 목록을 반환합니다.
            마지막 갱신일: 2026-05-24. API 지원 추가 시 업데이트 필요.
        """
        # Anthropic은 현재 공개 API로 모델 목록 조회를 지원하지 않음
        # 하드코딩된 목록 반환
        return [
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
        ]


def create_provider(
    provider_name: str,
    api_key: str,
    model_name: str,
    temperature: float = 0.7,
    max_output_tokens: Optional[int] = None,
) -> LLMProvider:
    """프로바이더 이름에 따라 적절한 프로바이더 인스턴스를 생성합니다.
    
    Args:
        provider_name: 프로바이더 이름 ("gemini", "openai", etc.)
        api_key: API 키
        model_name: 모델 이름
        temperature: 온도 설정
        max_output_tokens: 최대 출력 토큰 수
    
    Returns:
        LLMProvider 인스턴스
    
    Raises:
        ValueError: 지원하지 않는 프로바이더인 경우
    """
    provider_name = provider_name.lower()
    
    if provider_name == "gemini":
        return GeminiProvider(api_key, model_name, temperature, max_output_tokens)
    elif provider_name == "openai":
        return OpenAIProvider(api_key, model_name, temperature, max_output_tokens)
    elif provider_name == "anthropic":
        return AnthropicProvider(api_key, model_name, temperature, max_output_tokens)
    else:
        raise ValueError(f"지원하지 않는 프로바이더: {provider_name}. 지원되는 프로바이더: gemini, openai, anthropic")
