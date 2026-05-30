# In-Process Model Serving Project

## Overview

This project aims to convert the current subprocess-based model execution (RestoreFormer++, CodeFormer) to in-process execution to eliminate the 20-60 second model loading overhead on each request.

## Current Problem

- **Subprocess Execution**: Every request spawns a new Python process
- **Model Loading Overhead**: PyTorch models load on every request (20-60 seconds)
- **GPU VRAM Waste**: Multiple subprocesses can duplicate GPU memory usage
- **Performance Impact**: Significant latency for restoration operations

## Target Architecture

### Phase 1: Single Model In-Process Test
- Load CodeFormer model in-process (primary focus - more commonly used)
- Test single image restoration
- Measure performance improvement

### Phase 2: Model Caching & GPU Management
- Implement singleton pattern for model loading
- Add GPU memory management (model unloading)
- Thread-safe model access with locks

### Phase 3: Pipeline Integration
- Integrate in-process models into restoration pipeline
- Replace subprocess calls with direct model inference
- Handle error cases and fallback to subprocess

### Phase 4: Performance Optimization
- Benchmark performance improvements
- Optimize batch processing
- Add monitoring and metrics

## Project Structure

```
in-process-model-serving/
├── README.md
├── PLAN.md
├── src/
│   ├── model_loader.py      # Singleton model loader
│   ├── gpu_manager.py       # GPU memory management
│   ├── codeformer.py        # CodeFormer wrapper (Phase 1 focus)
│   ├── restoreformer.py     # RestoreFormer++ wrapper (Phase 2)
│   └── inference_server.py  # Optional: separate inference server
├── tests/
│   ├── test_model_loader.py
│   ├── test_codeformer.py
│   └── test_restoreformer.py
└── benchmarks/
    └── performance_comparison.py
```

## Dependencies

- PyTorch (already in project)
- torchscript/ONNX (for optimization)
- Additional GPU management libraries if needed

## Estimated Timeline

- **Phase 1**: 3-5 days
- **Phase 2**: 5-7 days
- **Phase 3**: 5-7 days
- **Phase 4**: 3-5 days
- **Total**: 16-24 days (3-4 weeks)

## Success Criteria

1. Model loading happens once at startup
2. Subsequent requests use cached models
3. Performance improvement: >80% reduction in restoration time
4. GPU memory usage: stable, no leaks
5. Thread-safe concurrent access

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| GPU memory exhaustion | Implement model unloading, memory monitoring |
| Thread safety issues | Use proper locking, test concurrent access |
| Model compatibility issues | Keep subprocess as fallback |
| Complex integration | Phase-wise approach, extensive testing |

## Fallback Strategy

If in-process execution encounters issues, maintain subprocess as fallback option with runtime configuration switch.
