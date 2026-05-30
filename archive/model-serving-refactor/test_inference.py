"""
Simple test script for CodeFormer in-process inference.

[PROJECT] In-Process Model Serving
[PHASE] Phase 1: Single Model In-Process Test
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Add src to path
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / "src"))

from codeformer import CodeFormer


def test_inference():
    """Test CodeFormer in-process inference with a sample image."""
    print("=" * 60)
    print("CodeFormer In-Process Inference Test")
    print("=" * 60)
    print()
    
    # Find a test image
    # Try to find an image in the project
    test_image = None
    possible_paths = [
        Path(__file__).parents[2] / "images" / "test.jpg",
        Path(__file__).parents[2] / "images" / "sample.jpg",
        Path(__file__).parents[2] / "images" / "input.jpg",
    ]
    
    for path in possible_paths:
        if path.exists():
            test_image = path
            break
    
    if test_image is None:
        print("No test image found. Please provide a test image path.")
        print("Looking for:")
        for path in possible_paths:
            print(f"  - {path}")
        print()
        print("Usage: python test_inference.py <image_path>")
        return False
    
    print(f"Test image: {test_image}")
    print()
    
    # Initialize model
    print("Initializing CodeFormer model...")
    model = CodeFormer()
    print(f"Device: {model.device}")
    print()
    
    # Load model
    print("Loading model (this may take a while for first run)...")
    print("Models to download:")
    print("  - CodeFormer: ~400MB")
    print("  - RealESRGAN: ~67MB (if bg_upsampler enabled)")
    print()
    
    start_load = time.time()
    try:
        model.load(fidelity=0.5, upscale=2, bg_upsampler="realesrgan")
        load_time = time.time() - start_load
        print(f"Model loaded in {load_time:.2f} seconds")
        print()
    except Exception as e:
        print(f"Failed to load model: {e}")
        return False
    
    # Run inference
    print("Running inference...")
    output_path = project_root / "test_output.png"
    
    start_inference = time.time()
    try:
        result = model(
            test_image,
            output_path,
            fidelity=0.5,
            upscale=2,
            bg_upsampler="realesrgan"
        )
        inference_time = time.time() - start_inference
        print(f"Inference completed in {inference_time:.2f} seconds")
        print(f"Output saved to: {result}")
        print()
    except Exception as e:
        print(f"Inference failed: {e}")
        return False
    
    # Summary
    print("=" * 60)
    print("Test Summary")
    print("=" * 60)
    print(f"Load time: {load_time:.2f} seconds")
    print(f"Inference time: {inference_time:.2f} seconds")
    print(f"Total time: {load_time + inference_time:.2f} seconds")
    print()
    print("SUCCESS: In-process inference completed!")
    print()
    
    return True


if __name__ == "__main__":
    # Check if image path provided
    if len(sys.argv) > 1:
        # Use provided image
        test_image = Path(sys.argv[1])
        if not test_image.exists():
            print(f"Image not found: {test_image}")
            sys.exit(1)
        
        # Override test
        project_root = Path(__file__).resolve().parent
        sys.path.insert(0, str(project_root / "src"))
        
        from codeformer import CodeFormer
        
        print("=" * 60)
        print("CodeFormer In-Process Inference Test")
        print("=" * 60)
        print()
        print(f"Test image: {test_image}")
        print()
        
        model = CodeFormer()
        print(f"Device: {model.device}")
        print()
        
        print("Loading model...")
        start_load = time.time()
        model.load(fidelity=0.5, upscale=2, bg_upsampler="realesrgan")
        load_time = time.time() - start_load
        print(f"Model loaded in {load_time:.2f} seconds")
        print()
        
        print("Running inference...")
        output_path = project_root / "test_output.png"
        start_inference = time.time()
        result = model(test_image, output_path, fidelity=0.5, upscale=2, bg_upsampler="realesrgan")
        inference_time = time.time() - start_inference
        print(f"Inference completed in {inference_time:.2f} seconds")
        print(f"Output saved to: {result}")
        print()
        
        print("=" * 60)
        print(f"Load time: {load_time:.2f} seconds")
        print(f"Inference time: {inference_time:.2f} seconds")
        print(f"Total time: {load_time + inference_time:.2f} seconds")
        print()
        print("SUCCESS!")
        sys.exit(0)
    else:
        # Run auto-detect test
        success = test_inference()
        sys.exit(0 if success else 1)
