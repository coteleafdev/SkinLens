"""
GPU Memory Manager

This module provides GPU memory monitoring and management for in-process model serving.

[PROJECT] In-Process Model Serving
[PHASE] Phase 2: Model Caching & GPU Management
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

import torch

log = logging.getLogger(__name__)


class GPUMemoryManager:
    """GPU memory manager for monitoring and managing GPU memory usage."""
    
    def __init__(self):
        """Initialize GPU memory manager."""
        self._lock = threading.Lock()
        self._device = None
        self._total_memory = 0
        self._reserved_memory = 0
        self._memory_threshold = 0.9  # 90% of total memory
        
        self._initialize()
    
    def _initialize(self) -> None:
        """Initialize GPU memory information."""
        if torch.cuda.is_available():
            self._device = torch.device("cuda")
            self._total_memory = torch.cuda.get_device_properties(0).total_memory
            log.info(f"GPU Memory Manager initialized: {self._total_memory / 1024**3:.2f} GB")
        else:
            log.warning("CUDA not available, GPU memory manager disabled")
    
    def get_memory_info(self) -> dict:
        """Get current GPU memory information.
        
        Returns:
            Dict with memory information (total, reserved, free, used).
        """
        if not torch.cuda.is_available():
            return {
                "total": 0,
                "reserved": 0,
                "free": 0,
                "used": 0,
                "available": False
            }
        
        with self._lock:
            reserved = torch.cuda.memory_reserved(0)
            allocated = torch.cuda.memory_allocated(0)
            free = self._total_memory - reserved
            
            return {
                "total": self._total_memory,
                "reserved": reserved,
                "allocated": allocated,
                "free": free,
                "used": allocated,
                "available": True
            }
    
    def get_memory_usage_percent(self) -> float:
        """Get current memory usage as percentage of total memory.
        
        Returns:
            Memory usage percentage (0.0 to 1.0).
        """
        if not torch.cuda.is_available():
            return 0.0
        
        info = self.get_memory_info()
        return info["reserved"] / info["total"] if info["total"] > 0 else 0.0
    
    def is_memory_available(self, required_bytes: int) -> bool:
        """Check if required memory is available.
        
        Args:
            required_bytes: Required memory in bytes.
        
        Returns:
            True if memory is available, False otherwise.
        """
        if not torch.cuda.is_available():
            return True  # CPU mode, always available
        
        info = self.get_memory_info()
        return info["free"] >= required_bytes
    
    def is_memory_threshold_exceeded(self) -> bool:
        """Check if memory usage exceeds threshold.
        
        Returns:
            True if usage exceeds threshold, False otherwise.
        """
        usage = self.get_memory_usage_percent()
        return usage >= self._memory_threshold
    
    def set_memory_threshold(self, threshold: float) -> None:
        """Set memory usage threshold.
        
        Args:
            threshold: Threshold value (0.0 to 1.0).
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("Threshold must be between 0.0 and 1.0")
        
        with self._lock:
            self._memory_threshold = threshold
            log.info(f"Memory threshold set to {threshold * 100:.1f}%")
    
    def empty_cache(self) -> None:
        """Empty CUDA cache to free unused memory."""
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            log.debug("CUDA cache emptied")
    
    def get_memory_summary(self) -> str:
        """Get human-readable memory summary.
        
        Returns:
            Formatted memory summary string.
        """
        info = self.get_memory_info()
        
        if not info["available"]:
            return "GPU not available"
        
        total_gb = info["total"] / 1024**3
        reserved_gb = info["reserved"] / 1024**3
        allocated_gb = info["allocated"] / 1024**3
        free_gb = info["free"] / 1024**3
        usage_percent = self.get_memory_usage_percent() * 100
        
        return (
            f"GPU Memory: {total_gb:.2f} GB total\n"
            f"  Reserved: {reserved_gb:.2f} GB ({usage_percent:.1f}%)\n"
            f"  Allocated: {allocated_gb:.2f} GB\n"
            f"  Free: {free_gb:.2f} GB"
        )


# Global singleton instance
_gpu_manager: Optional[GPUMemoryManager] = None


def get_gpu_manager() -> GPUMemoryManager:
    """Get the global GPU memory manager singleton instance."""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUMemoryManager()
    return _gpu_manager
