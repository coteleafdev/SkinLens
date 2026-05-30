"""
Tests for RestoreFormer++ in-process wrapper.

[PROJECT] In-Process Model Serving
[PHASE] Phase 1: Single Model In-Process Test
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Add project src to path
import sys
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "model-serving-refactor" / "src"))

from restoreformer import RestoreFormerPlusPlus


def test_restoreformer_initialization():
    """Test RestoreFormer++ wrapper initialization."""
    # This will fail if repository not found, which is expected in Phase 1
    try:
        model = RestoreFormerPlusPlus()
        print(f"[OK] RestoreFormer++ initialized (device: {model.device})")
    except FileNotFoundError as e:
        print(f"[WARN] Repository not found (expected in Phase 1): {e}")
        pytest.skip("RestoreFormer++ repository not found")


def test_restoreformer_device_selection():
    """Test device selection logic."""
    try:
        # Test auto device selection
        model_auto = RestoreFormerPlusPlus(device=None)
        print(f"[OK] Auto device: {model_auto.device}")
        
        # Test explicit CPU
        model_cpu = RestoreFormerPlusPlus(device="cpu")
        assert model_cpu.device == "cpu"
        print(f"[OK] CPU device: {model_cpu.device}")
        
    except FileNotFoundError:
        pytest.skip("RestoreFormer++ repository not found")


def test_restoreformer_load_not_implemented():
    """Test that load() raises NotImplementedError in Phase 1."""
    try:
        model = RestoreFormerPlusPlus()
        with pytest.raises(NotImplementedError):
            model.load()
        print("[OK] load() raises NotImplementedError as expected (Phase 1)")
    except FileNotFoundError:
        pytest.skip("RestoreFormer++ repository not found")


def test_restoreformer_call_not_loaded():
    """Test that __call__ raises RuntimeError when model not loaded."""
    try:
        model = RestoreFormerPlusPlus()
        with pytest.raises(RuntimeError, match="Model not loaded"):
            model(Path("dummy.jpg"), Path("output.jpg"))
        print("[OK] __call__ raises RuntimeError when not loaded")
    except FileNotFoundError:
        pytest.skip("RestoreFormer++ repository not found")


if __name__ == "__main__":
    print("Running RestoreFormer++ wrapper tests...")
    print()
    
    test_restoreformer_initialization()
    test_restoreformer_device_selection()
    test_restoreformer_load_not_implemented()
    test_restoreformer_call_not_loaded()
    
    print("\nAll tests completed!")
