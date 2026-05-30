"""
Model Loader - Singleton pattern for in-process model serving.

This module provides thread-safe, singleton-based model loading for
RestoreFormer++ and CodeFormer models to eliminate subprocess overhead.

[PROJECT] In-Process Model Serving
[PHASE] Phase 1: Single Model In-Process Test
"""
from __future__ import annotations

import logging
import threading
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)


class ModelType(Enum):
    """Supported model types."""
    RESTOREFORMER = auto()
    CODEFORMER = auto()


class ModelState(Enum):
    """Model loading states."""
    NOT_LOADED = auto()
    LOADING = auto()
    LOADED = auto()
    ERROR = auto()


class ModelLoader:
    """Singleton model loader with thread-safe access.
    
    This class implements the singleton pattern to ensure models are
    loaded only once and shared across all requests.
    """
    
    _instance: Optional["ModelLoader"] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> "ModelLoader":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._initialized = True
        self._models: Dict[ModelType, Any] = {}
        self._model_states: Dict[ModelType, ModelState] = {
            ModelType.RESTOREFORMER: ModelState.NOT_LOADED,
            ModelType.CODEFORMER: ModelState.NOT_LOADED,
        }
        self._model_locks: Dict[ModelType, threading.Lock] = {
            ModelType.RESTOREFORMER: threading.Lock(),
            ModelType.CODEFORMER: threading.Lock(),
        }
        
        log.info("ModelLoader singleton initialized")
    
    def load_restoreformer(self, repo_path: Optional[Path] = None) -> Any:
        """Load RestoreFormer++ model in-process.
        
        Args:
            repo_path: Path to RestoreFormer++ repository.
                      If None, uses default path.
        
        Returns:
            Loaded model instance, or None if subprocess should be used.
        
        Raises:
            RuntimeError: If model loading fails.
        """
        model_type = ModelType.RESTOREFORMER
        
        # Return cached model if already loaded
        if self._model_states[model_type] == ModelState.LOADED:
            log.debug("RestoreFormer++ already loaded, returning cached model")
            return self._models[model_type]
        
        # Check if currently loading (avoid concurrent loading)
        if self._model_states[model_type] == ModelState.LOADING:
            log.warning("RestoreFormer++ currently loading, waiting...")
            # Simple wait - in production, use condition variable
            import time
            for _ in range(30):  # Wait up to 30 seconds
                time.sleep(1)
                if self._model_states[model_type] == ModelState.LOADED:
                    return self._models[model_type]
            raise RuntimeError("RestoreFormer++ loading timeout")
        
        # Load model
        with self._model_locks[model_type]:
            # Double-check after acquiring lock
            if self._model_states[model_type] == ModelState.LOADED:
                return self._models[model_type]
            
            self._model_states[model_type] = ModelState.LOADING
            log.info("Loading RestoreFormer++ model in-process...")
            
            try:
                model = self._load_restoreformer_impl(repo_path)
                
                # If model is None, use subprocess fallback
                if model is None:
                    self._model_states[model_type] = ModelState.NOT_LOADED
                    log.info("RestoreFormer++ in-process not available, will use subprocess")
                    return None
                
                self._models[model_type] = model
                self._model_states[model_type] = ModelState.LOADED
                log.info("RestoreFormer++ model loaded successfully")
                return model
                
            except Exception as e:
                self._model_states[model_type] = ModelState.ERROR
                log.error(f"Failed to load RestoreFormer++: {e}")
                raise RuntimeError(f"RestoreFormer++ loading failed: {e}") from e
    
    def _load_restoreformer_impl(self, repo_path: Optional[Path]) -> Any:
        """Actual RestoreFormer++ loading implementation.
        
        [PHASE 2] RestoreFormer++ is less commonly used than CodeFormer.
        For now, this returns None to indicate subprocess should be used as fallback.
        """
        log.info("RestoreFormer++ in-process not implemented, will use subprocess fallback")
        return None  # Signal to use subprocess
    
    def load_codeformer(self, repo_path: Optional[Path] = None) -> Any:
        """Load CodeFormer model in-process.
        
        Args:
            repo_path: Path to CodeFormer repository.
                      If None, uses default path.
        
        Returns:
            Loaded model instance.
        
        Raises:
            RuntimeError: If model loading fails.
        """
        model_type = ModelType.CODEFORMER
        
        # Return cached model if already loaded
        if self._model_states[model_type] == ModelState.LOADED:
            log.debug("CodeFormer already loaded, returning cached model")
            return self._models[model_type]
        
        # Load model
        with self._model_locks[model_type]:
            if self._model_states[model_type] == ModelState.LOADED:
                return self._models[model_type]
            
            self._model_states[model_type] = ModelState.LOADING
            log.info("Loading CodeFormer model in-process...")
            
            try:
                # TODO: Implement actual model loading (Phase 2)
                model = self._load_codeformer_impl(repo_path)
                
                self._models[model_type] = model
                self._model_states[model_type] = ModelState.LOADED
                log.info("CodeFormer model loaded successfully")
                return model
                
            except Exception as e:
                self._model_states[model_type] = ModelState.ERROR
                log.error(f"Failed to load CodeFormer: {e}")
                raise RuntimeError(f"CodeFormer loading failed: {e}") from e
    
    def _load_codeformer_impl(self, repo_path: Optional[Path]) -> Any:
        """Actual CodeFormer loading implementation.
        
        [PHASE 1] Implemented using CodeFormer wrapper.
        """
        from codeformer import CodeFormer
        
        model = CodeFormer(repo_path=repo_path)
        model.load()
        return model
    
    def unload_model(self, model_type: ModelType) -> None:
        """Unload a model to free GPU memory.
        
        Args:
            model_type: Model type to unload.
        """
        with self._model_locks[model_type]:
            if self._model_states[model_type] == ModelState.LOADED:
                model = self._models[model_type]
                
                # Call model's unload method if available
                if hasattr(model, 'unload'):
                    model.unload()
                else:
                    # Generic cleanup
                    del model
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()
                
                del self._models[model_type]
                self._model_states[model_type] = ModelState.NOT_LOADED
                log.info(f"{model_type.name} model unloaded")
    
    def get_memory_info(self) -> dict:
        """Get current GPU memory information.
        
        Returns:
            Dict with memory information.
        """
        from gpu_manager import get_gpu_manager
        return get_gpu_manager().get_memory_info()
    
    def should_unload_for_memory(self, model_type: ModelType) -> bool:
        """Check if model should be unloaded due to memory pressure.
        
        Args:
            model_type: Model type to check.
        
        Returns:
            True if model should be unloaded, False otherwise.
        """
        from gpu_manager import get_gpu_manager
        gpu_mgr = get_gpu_manager()
        
        # Unload if memory threshold exceeded
        if gpu_mgr.is_memory_threshold_exceeded():
            log.warning(f"Memory threshold exceeded, unloading {model_type.name}")
            return True
        
        return False
    
    def get_model_state(self, model_type: ModelType) -> ModelState:
        """Get current state of a model.
        
        Args:
            model_type: Model type to check.
        
        Returns:
            Current model state.
        """
        return self._model_states[model_type]


# Global singleton instance
_model_loader: Optional[ModelLoader] = None


def get_model_loader() -> ModelLoader:
    """Get the global ModelLoader singleton instance."""
    global _model_loader
    if _model_loader is None:
        _model_loader = ModelLoader()
    return _model_loader
