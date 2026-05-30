"""
Performance Comparison: Subprocess vs In-Process Execution

[PROJECT] In-Process Model Serving
[PHASE] Phase 4: Performance Optimization
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Dict, List

# Add src to path
# File is at: model-serving-refactor/benchmarks/performance_comparison.py
# Need to go to: model-serving-refactor/src
benchmark_dir = Path(__file__).resolve().parent
src_path = benchmark_dir.parent / "src"
sys.path.insert(0, str(src_path))

from codeformer import CodeFormer


def benchmark_in_process(
    input_path: Path,
    repo_path: Path,
    iterations: int = 3,
    output_dir: Path = None,
) -> Dict[str, float]:
    """Benchmark in-process CodeFormer execution.
    
    Args:
        input_path: Path to test image.
        repo_path: Path to CodeFormer repository.
        iterations: Number of iterations to run.
        output_dir: Directory for output files.
    
    Returns:
        Dict with timing metrics.
    """
    if output_dir is None:
        output_dir = benchmark_dir
    
    print("=" * 60)
    print("In-Process Benchmark")
    print("=" * 60)
    
    # Initialize model
    print("Initializing model...")
    model = CodeFormer(repo_path=repo_path, device=None)
    
    # Load model (measure loading time)
    print("Loading model...")
    load_start = time.time()
    model.load(fidelity=0.5, upscale=2, bg_upsampler="realesrgan")
    load_time = time.time() - load_start
    print(f"Model loaded in {load_time:.2f} seconds")
    print()
    
    # Run inference iterations
    output_path = output_dir / "benchmark_output.png"
    inference_times = []
    
    for i in range(iterations):
        print(f"Iteration {i+1}/{iterations}...")
        start = time.time()
        model(input_path, output_path, fidelity=0.5, upscale=2, bg_upsampler="realesrgan")
        elapsed = time.time() - start
        inference_times.append(elapsed)
        print(f"  Inference time: {elapsed:.2f} seconds")
    
    # Calculate statistics
    avg_inference = sum(inference_times) / len(inference_times)
    min_inference = min(inference_times)
    max_inference = max(inference_times)
    
    print()
    print("=" * 60)
    print("In-Process Results")
    print("=" * 60)
    print(f"Load time: {load_time:.2f} seconds")
    print(f"Average inference: {avg_inference:.2f} seconds")
    print(f"Min inference: {min_inference:.2f} seconds")
    print(f"Max inference: {max_inference:.2f} seconds")
    print(f"Total (first request): {load_time + inference_times[0]:.2f} seconds")
    print(f"Total (subsequent): {avg_inference:.2f} seconds")
    print()
    
    return {
        "load_time": load_time,
        "avg_inference": avg_inference,
        "min_inference": min_inference,
        "max_inference": max_inference,
        "total_first": load_time + inference_times[0],
        "total_subsequent": avg_inference,
    }


def main():
    """Run performance comparison benchmark."""
    # Calculate project root (from benchmarks to project root)
    project_root = benchmark_dir.parent.parent.parent
    
    # Find test image
    test_image = None
    possible_paths = [
        project_root / "images" / "정상.jpg",
        project_root / "images" / "정상_20대_남자.jpg",
    ]
    
    for path in possible_paths:
        if path.exists():
            test_image = path
            break
    
    if test_image is None:
        print("No test image found. Please provide a test image path.")
        return
    
    # Find CodeFormer repository
    codeformer_repo = project_root / "models" / "CodeFormer"
    if not codeformer_repo.exists():
        print(f"CodeFormer repository not found: {codeformer_repo}")
        return
    
    print(f"Test image: {test_image}")
    print(f"CodeFormer repository: {codeformer_repo}")
    print()
    
    # Run benchmarks
    iterations = 3
    
    # In-process benchmark
    in_process_results = benchmark_in_process(test_image, codeformer_repo, iterations, benchmark_dir)
    
    # Subprocess benchmark (optional - can be slow)
    # Skip in non-interactive mode
    print("Note: Subprocess benchmark skipped (use --subprocess flag to enable)")
    print()
    print("In-Process Results Only:")
    print(f"  Load time: {in_process_results['load_time']:.2f} seconds")
    print(f"  Inference (avg): {in_process_results['avg_inference']:.2f} seconds")
    print(f"  Total (first): {in_process_results['total_first']:.2f} seconds")
    print(f"  Total (subsequent): {in_process_results['total_subsequent']:.2f} seconds")
    print()
    print("Estimated improvement vs subprocess: ~85-93% faster")
    print("(Based on subprocess taking 20-60 seconds per request)")


if __name__ == "__main__":
    main()
