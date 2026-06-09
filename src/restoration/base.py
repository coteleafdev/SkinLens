# -*- coding: utf-8 -*-
"""
src.restoration.base — 얼굴 복원 백엔드 추상 인터페이스

Strategy Pattern을 사용하여 다양한 복원 알고리즘을 유연하게 교체할 수 있습니다.

[EXTENSION 2026-05-24] 향후 새로운 복원 엔진 추가를 위한 추상화 계층 강화.
- 전처리/후처리 훅 메서드 추가
- 모델 로드/언로드 라이프사이클 메서드 추가
- 설정 유효성 검사 강화
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Optional, Callable


class BaseRestorer(ABC):
    """얼굴 복원 백엔드 추상 기반 클래스.
    
    새로운 복원 엔진을 추가할 때 이 클래스를 상속받아 구현하세요.
    
    구현 가이드:
        1. __init__(config): 설정 초기화
        2. load_model(): 모델 로드 (필요시)
        3. restore(input_path, output_path, **kwargs): 복원 수행
        4. get_name(), get_version(): 메타데이터
        5. preprocess(input_path): 전처리 (선택)
        6. postprocess(output_path): 후처리 (선택)
        7. cleanup(): 리소스 정리 (선택)
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """복원 백엔드 초기화.
        
        Args:
            config: 복원 백엔드 설정
                - repo: 모델 레포 경로 (필수)
                - device: 디바이스 ("cuda", "cpu", "auto")
                - 기타 엔진별 파라미터
        """
        self.config = config or {}
        self._model_loaded = False
    
    @abstractmethod
    def restore(
        self,
        input_path: str | Path,
        output_path: str | Path,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """얼굴 복원 수행.
        
        Args:
            input_path: 입력 이미지 경로
            output_path: 출력 이미지 경로
            **kwargs: 추가 파라미터 (백엔드별 상이)
        
        Returns:
            복원 결과 딕셔너리
                - output_path: 출력 경로
                - 기타 엔진별 메타데이터
        """
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """복원 백엔드 이름."""
        pass
    
    @abstractmethod
    def get_version(self) -> str:
        """알고리즘 버전."""
        pass
    
    def load_model(self) -> None:
        """모델 로드 (선택적).
        
        기본 구현은 아무것도 하지 않습니다. in-process 실행을 위해
        모델을 미리 로드해야 하는 엔진에서 오버라이드하세요.
        """
        self._model_loaded = True
    
    def unload_model(self) -> None:
        """모델 언로드 (선택적).
        
        기본 구현은 아무것도 하지 않습니다. 메모리 해제가 필요한
        엔진에서 오버라이드하세요.
        """
        self._model_loaded = False
    
    def preprocess(self, input_path: Path) -> Path:
        """전처리 (선택적).
        
        Args:
            input_path: 입력 이미지 경로
        
        Returns:
            전처리된 이미지 경로 (변경 없으면 input_path 반환)
        """
        return input_path
    
    def postprocess(self, output_path: Path) -> Path:
        """후처리 (선택적).
        
        Args:
            output_path: 출력 이미지 경로
        
        Returns:
            후처리된 이미지 경로 (변경 없으면 output_path 반환)
        """
        return output_path
    
    def cleanup(self) -> None:
        """리소스 정리 (선택적).
        
        엔진 사용 후 호출되어 임시 파일 정리 등을 수행합니다.
        """
        pass
    
    def get_config(self, key: str, default=None):
        """설정 값을 가져옵니다.
        
        Args:
            key: 설정 키
            default: 기본값
        
        Returns:
            설정 값 또는 기본값
        """
        return self.config.get(key, default)
    
    def validate_config(self, required_keys: list[str]) -> None:
        """설정 유효성 검사.
        
        Args:
            required_keys: 필수 키 목록
        
        Raises:
            ValueError: 필수 키가 없는 경우
        """
        missing_keys = [key for key in required_keys if key not in self.config]
        if missing_keys:
            raise ValueError(f"필수 설정 키가 없습니다: {missing_keys}")
    
    def is_model_loaded(self) -> bool:
        """모델 로드 상태 확인."""
        return self._model_loaded
    
    def get_supported_devices(self) -> list[str]:
        """지원하는 디바이스 목록 반환.
        
        Returns:
            지원 디바이스 리스트 (예: ["cuda", "cpu"])
        """
        return ["cpu"]  # 기본값
