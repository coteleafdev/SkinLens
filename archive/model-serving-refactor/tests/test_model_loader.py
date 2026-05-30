"""
Tests for ModelLoader singleton pattern.

[PROJECT] In-Process Model Serving
[PHASE] Phase 1: Single Model In-Process Test
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

# Add project src to path
import sys
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "model-serving-refactor" / "src"))

from model_loader import ModelLoader, ModelType, ModelState, get_model_loader


def test_singleton_pattern():
    """Test that ModelLoader is a singleton."""
    loader1 = ModelLoader()
    loader2 = ModelLoader()
    
    assert loader1 is loader2, "ModelLoader should be singleton"


def test_get_model_loader():
    """Test get_model_loader returns singleton."""
    loader1 = get_model_loader()
    loader2 = get_model_loader()
    
    assert loader1 is loader2, "get_model_loader should return same instance"


def test_initial_state():
    """Test initial model states."""
    loader = get_model_loader()
    
    assert loader.get_model_state(ModelType.RESTOREFORMER) == ModelState.NOT_LOADED
    assert loader.get_model_state(ModelType.CODEFORMER) == ModelState.NOT_LOADED


def test_model_state_not_loaded():
    """Test that attempting to load fails with NotImplementedError (Phase 1)."""
    loader = get_model_loader()
    
    with pytest.raises(NotImplementedError):
        loader.load_restoreformer()


def test_thread_safety():
    """Test that concurrent loading attempts are handled safely."""
    loader = get_model_loader()
    errors = []
    
    def try_load():
        try:
            loader.load_restoreformer()
        except NotImplementedError:
            # Expected in Phase 1
            pass
        except Exception as e:
            errors.append(e)
    
    threads = [threading.Thread(target=try_load) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Should not have any race condition errors
    assert len(errors) == 0, f"Thread safety errors: {errors}"


def test_model_unload():
    """Test model unloading."""
    loader = get_model_loader()
    
    # Try to unload even though not loaded (should be safe)
    loader.unload_model(ModelType.RESTOREFORMER)
    
    assert loader.get_model_state(ModelType.RESTOREFORMER) == ModelState.NOT_LOADED


if __name__ == "__main__":
    # Run basic tests
    print("Running ModelLoader tests...")
    
    test_singleton_pattern()
    print("[OK] Singleton pattern test passed")
    
    test_get_model_loader()
    print("[OK] get_model_loader test passed")
    
    test_initial_state()
    print("[OK] Initial state test passed")
    
    test_model_state_not_loaded()
    print("[OK] Model state test passed (expected NotImplementedError)")
    
    test_thread_safety()
    print("[OK] Thread safety test passed")
    
    test_model_unload()
    print("[OK] Model unload test passed")
    
    print("\nAll basic tests passed!")
