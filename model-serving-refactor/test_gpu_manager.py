"""
Test script for GPU Memory Manager.

[PROJECT] In-Process Model Serving
[PHASE] Phase 2: Model Caching & GPU Management
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))

from gpu_manager import get_gpu_manager


def test_gpu_manager():
    """Test GPU memory manager functionality."""
    print("=" * 60)
    print("GPU Memory Manager Test")
    print("=" * 60)
    print()
    
    # Get GPU manager
    gpu_mgr = get_gpu_manager()
    
    # Get memory info
    print("Memory Information:")
    info = gpu_mgr.get_memory_info()
    if info["available"]:
        print(f"  Total: {info['total'] / 1024**3:.2f} GB")
        print(f"  Reserved: {info['reserved'] / 1024**3:.2f} GB")
        print(f"  Allocated: {info['allocated'] / 1024**3:.2f} GB")
        print(f"  Free: {info['free'] / 1024**3:.2f} GB")
    else:
        print("  GPU not available")
    print()
    
    # Get memory usage percentage
    usage = gpu_mgr.get_memory_usage_percent()
    print(f"Memory Usage: {usage * 100:.1f}%")
    print()
    
    # Check threshold
    threshold_exceeded = gpu_mgr.is_memory_threshold_exceeded()
    print(f"Threshold Exceeded: {threshold_exceeded}")
    print()
    
    # Get summary
    print("Memory Summary:")
    print(gpu_mgr.get_memory_summary())
    print()
    
    # Test empty cache
    print("Testing empty cache...")
    gpu_mgr.empty_cache()
    print("Cache emptied")
    print()
    
    # Test threshold setting
    print("Testing threshold setting...")
    gpu_mgr.set_memory_threshold(0.8)
    print("Threshold set to 80%")
    print()
    
    print("=" * 60)
    print("GPU Memory Manager Test Complete")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    success = test_gpu_manager()
    sys.exit(0 if success else 1)
