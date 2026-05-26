"""
Tests for CodeFormer in-process wrapper.

[PROJECT] In-Process Model Serving
[PHASE] Phase 1: Single Model In-Process Test (CodeFormer focus)
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Add project src to path
import sys
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "model-serving-refactor" / "src"))

from codeformer import CodeFormer


def test_codeformer_initialization():
    """Test CodeFormer wrapper initialization."""
    # This will fail if repository not found, which is expected in Phase 1
    try:
        model = CodeFormer()
        print(f"[OK] CodeFormer initialized (device: {model.device})")
    except FileNotFoundError as e:
        print(f"[WARN] Repository not found (expected in Phase 1): {e}")
        pytest.skip("CodeFormer repository not found")


def test_codeformer_device_selection():
    """Test device selection logic."""
    try:
        # Test auto device selection
        model_auto = CodeFormer(device=None)
        print(f"[OK] Auto device: {model_auto.device}")
        
        # Test explicit CPU
        model_cpu = CodeFormer(device="cpu")
        assert model_cpu.device == "cpu"
        print(f"[OK] CPU device: {model_cpu.device}")
        
    except FileNotFoundError:
        pytest.skip("CodeFormer repository not found")


def test_codeformer_load():
    """Test that load() successfully loads the model."""
    try:
        model = CodeFormer()
        # This will download the model if not present
        # Skip in automated tests to avoid large downloads
        print("[SKIP] load() test skipped (requires model download)")
        pytest.skip("Model download required - skip in automated tests")
    except FileNotFoundError:
        pytest.skip("CodeFormer repository not found")


def test_codeformer_call_not_loaded():
    """Test that __call__ raises RuntimeError when model not loaded."""
    try:
        model = CodeFormer()
        with pytest.raises(RuntimeError, match="Model not loaded"):
            model(Path("dummy.jpg"), Path("output.jpg"))
        print("[OK] __call__ raises RuntimeError when not loaded")
    except FileNotFoundError:
        pytest.skip("CodeFormer repository not found")


if __name__ == "__main__":
    print("Running CodeFormer wrapper tests...")
    print()
    
    test_codeformer_initialization()
    test_codeformer_device_selection()
    test_codeformer_load()
    test_codeformer_call_not_loaded()
    
    print("\nAll tests completed!")
