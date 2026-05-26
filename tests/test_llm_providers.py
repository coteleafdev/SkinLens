"""
test_llm_providers.py — LLM 프로바이더 단위 테스트

OpenAIProvider, GeminiProvider의 기본 기능을 테스트합니다.
Mock을 사용하여 실제 API 호출 없이 테스트합니다.
"""

from __future__ import annotations

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Any, Dict, List

from src.llm.llm_providers import (
    LLMProvider,
    GeminiProvider,
    OpenAIProvider,
    AnthropicProvider,
    create_provider,
)


class TestGeminiProvider:
    """GeminiProvider 단위 테스트."""

    def test_init(self) -> None:
        """초기화 테스트."""
        provider = GeminiProvider(
            api_key="test_key",
            model_name="gemini-2.5-flash",
            temperature=0.7,
            max_output_tokens=1000,
        )
        assert provider.api_key == "test_key"
        assert provider.model_name == "gemini-2.5-flash"
        assert provider.temperature == 0.7
        assert provider.max_output_tokens == 1000
        assert provider._client is None

    def test_configure(self) -> None:
        """configure() 메서드 테스트 (실제 패키지 필요)."""
        try:
            provider = GeminiProvider(api_key="test_key", model_name="gemini-2.5-flash")
            provider.configure()
            assert provider._client is not None
            assert provider._genai is not None
        except ImportError:
            pytest.skip("google.generativeai 패키지가 설치되지 않음")

    def test_generate_content(self) -> None:
        """generate_content() 메서드 테스트 (실제 패키지 필요)."""
        try:
            provider = GeminiProvider(api_key="test_key", model_name="gemini-2.5-flash")
            provider.configure()
            # 실제 API 호출 없이 메서드 존재 확인만 수행
            assert hasattr(provider, "generate_content")
        except ImportError:
            pytest.skip("google.generativeai 패키지가 설치되지 않음")

    def test_list_models(self) -> None:
        """list_models() 메서드 테스트 (실제 패키지 필요)."""
        try:
            provider = GeminiProvider(api_key="test_key", model_name="gemini-2.5-flash")
            provider.configure()
            # 실제 API 호출 없이 메서드 존재 확인만 수행
            assert hasattr(provider, "list_models")
        except ImportError:
            pytest.skip("google.generativeai 패키지가 설치되지 않음")

    def test_import_error_without_package(self) -> None:
        """google.generativeai 패키지가 없을 때 ImportError 테스트."""
        with patch.dict("sys.modules", {"google": None, "google.generativeai": None}):
            provider = GeminiProvider(api_key="test_key", model_name="gemini-2.5-flash")
            with pytest.raises(ImportError, match="google.generativeai"):
                provider.configure()


class TestOpenAIProvider:
    """OpenAIProvider 단위 테스트."""

    def test_init(self) -> None:
        """초기화 테스트."""
        provider = OpenAIProvider(
            api_key="test_key",
            model_name="gpt-4o",
            temperature=0.7,
            max_output_tokens=1000,
        )
        assert provider.api_key == "test_key"
        assert provider.model_name == "gpt-4o"
        assert provider.temperature == 0.7
        assert provider.max_output_tokens == 1000
        assert provider._client is None

    @patch("openai.OpenAI")
    def test_configure(self, mock_openai: Any) -> None:
        """configure() 메서드 테스트."""
        provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o")
        provider.configure()
        
        assert mock_openai.called
        assert provider._client is not None

    @patch("openai.OpenAI")
    def test_generate_content_text_only(self, mock_openai: Any) -> None:
        """텍스트 전용 generate_content() 테스트."""
        # Mock 설정
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "Test response"
        mock_choice.message = mock_message
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai.return_value = mock_client
        
        provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o")
        provider.configure()
        
        result = provider.generate_content(
            prompts=["system prompt", "user prompt"],
            images=[],
        )
        
        assert result == "Test response"
        mock_client.chat.completions.create.assert_called_once()

    def test_generate_content_with_images(self) -> None:
        """이미지 포함 generate_content() 테스트 (실제 패키지 필요)."""
        try:
            provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o")
            provider.configure()
            # 실제 API 호출 없이 메서드 존재 확인만 수행
            assert hasattr(provider, "generate_content")
        except ImportError:
            pytest.skip("openai 패키지가 설치되지 않음")

    def test_list_models(self) -> None:
        """list_models() 메서드 테스트 (실제 패키지 필요)."""
        try:
            provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o")
            provider.configure()
            # 실제 API 호출 없이 메서드 존재 확인만 수행
            assert hasattr(provider, "list_models")
        except ImportError:
            pytest.skip("openai 패키지가 설치되지 않음")

    def test_import_error_without_package(self) -> None:
        """openai 패키지가 없을 때 ImportError 테스트."""
        with patch.dict("sys.modules", {"openai": None}):
            provider = OpenAIProvider(api_key="test_key", model_name="gpt-4o")
            with pytest.raises(ImportError, match="openai"):
                provider.configure()


class TestAnthropicProvider:
    """AnthropicProvider 단위 테스트."""

    def test_init(self) -> None:
        """초기화 테스트."""
        provider = AnthropicProvider(
            api_key="test_key",
            model_name="claude-3-5-sonnet-20241022",
            temperature=0.7,
            max_output_tokens=1000,
        )
        assert provider.api_key == "test_key"
        assert provider.model_name == "claude-3-5-sonnet-20241022"
        assert provider.temperature == 0.7
        assert provider.max_output_tokens == 1000
        assert provider._client is None

    def test_configure(self) -> None:
        """configure() 메서드 테스트 (실제 패키지 필요)."""
        try:
            provider = AnthropicProvider(api_key="test_key", model_name="claude-3-5-sonnet-20241022")
            provider.configure()
            assert provider._client is not None
        except ImportError:
            pytest.skip("anthropic 패키지가 설치되지 않음")

    def test_generate_content(self) -> None:
        """generate_content() 메서드 테스트 (실제 패키지 필요)."""
        try:
            provider = AnthropicProvider(api_key="test_key", model_name="claude-3-5-sonnet-20241022")
            provider.configure()
            # 실제 API 호출 없이 메서드 존재 확인만 수행
            assert hasattr(provider, "generate_content")
        except ImportError:
            pytest.skip("anthropic 패키지가 설치되지 않음")

    def test_list_models(self) -> None:
        """list_models() 메서드 테스트."""
        provider = AnthropicProvider(api_key="test_key", model_name="claude-3-5-sonnet-20241022")
        models = provider.list_models()
        
        # 하드코딩된 목록 반환 확인
        assert len(models) == 5
        assert "claude-3-5-sonnet-20241022" in models
        assert "claude-3-5-haiku-20241022" in models

    def test_import_error_without_package(self) -> None:
        """anthropic 패키지가 없을 때 ImportError 테스트."""
        with patch.dict("sys.modules", {"anthropic": None}):
            provider = AnthropicProvider(api_key="test_key", model_name="claude-3-5-sonnet-20241022")
            with pytest.raises(ImportError, match="anthropic"):
                provider.configure()


class TestCreateProvider:
    """create_provider() 팩토리 함수 테스트."""

    def test_create_gemini_provider(self) -> None:
        """Gemini 프로바이더 생성 테스트."""
        provider = create_provider(
            provider_name="gemini",
            api_key="test_key",
            model_name="gemini-2.5-flash",
        )
        assert isinstance(provider, GeminiProvider)
        assert provider.api_key == "test_key"
        assert provider.model_name == "gemini-2.5-flash"

    def test_create_openai_provider(self) -> None:
        """OpenAI 프로바이더 생성 테스트."""
        provider = create_provider(
            provider_name="openai",
            api_key="test_key",
            model_name="gpt-4o",
        )
        assert isinstance(provider, OpenAIProvider)
        assert provider.api_key == "test_key"
        assert provider.model_name == "gpt-4o"

    def test_create_anthropic_provider(self) -> None:
        """Anthropic 프로바이더 생성 테스트."""
        provider = create_provider(
            provider_name="anthropic",
            api_key="test_key",
            model_name="claude-3-5-sonnet-20241022",
        )
        assert isinstance(provider, AnthropicProvider)
        assert provider.api_key == "test_key"
        assert provider.model_name == "claude-3-5-sonnet-20241022"

    def test_create_provider_invalid_name(self) -> None:
        """지원하지 않는 프로바이더 이름 테스트."""
        with pytest.raises(ValueError, match="지원하지 않는 프로바이더"):
            create_provider(
                provider_name="invalid",
                api_key="test_key",
                model_name="model",
            )

    def test_create_provider_case_insensitive(self) -> None:
        """대소문자 구분 없이 프로바이더 생성 테스트."""
        provider1 = create_provider("GEMINI", "test_key", "gemini-2.5-flash")
        provider2 = create_provider("OpenAI", "test_key", "gpt-4o")
        provider3 = create_provider("ANTHROPIC", "test_key", "claude-3-5-sonnet-20241022")
        
        assert isinstance(provider1, GeminiProvider)
        assert isinstance(provider2, OpenAIProvider)
        assert isinstance(provider3, AnthropicProvider)


class TestLLMProviderABC:
    """LLMProvider 추상 클래스 테스트."""

    def test_cannot_instantiate_abc(self) -> None:
        """추상 클래스 직접 인스턴스화 불가 테스트."""
        with pytest.raises(TypeError):
            LLMProvider(api_key="test", model_name="model")
