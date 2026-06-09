"""
Image API endpoints for serving images from local DB and Supabase.
"""
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import FileResponse

from src.storage.local_db import LocalImageStorage
from src.storage.supabase_storage import SupabaseImageStorage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/images", tags=["images"])

# Initialize storage instances
local_storage = LocalImageStorage()
supabase_storage: Optional[SupabaseImageStorage] = None

# Try to initialize Supabase if credentials are available and enabled
try:
    from src.config.config_manager import ConfigManager
    config = ConfigManager()
    image_storage_config = config.get("image_storage", {}).get("supabase", {})
    
    if image_storage_config.get("enabled", False):
        supabase_storage = SupabaseImageStorage()
        log.info("Supabase storage initialized for images API")
    else:
        log.info("Supabase storage disabled, using local storage only")
except Exception as e:
    log.warning(f"Failed to initialize Supabase storage: {e}")


@router.get("/{customer_id}/original")
async def get_original_image(customer_id: str) -> Response:
    """
    Get original image for a customer.
    
    Args:
        customer_id: Customer ID
    
    Returns:
        Image binary data
    """
    # Try Supabase first
    if supabase_storage:
        supabase_url = supabase_storage.get_image_url(customer_id, "original")
        if supabase_url:
            # Redirect to Supabase URL
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=supabase_url)
    
    # Fallback to local storage
    image_data = local_storage.get_image_binary(customer_id, "original")
    if image_data:
        return Response(content=image_data, media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Original image not found")


@router.get("/{customer_id}/restored")
async def get_restored_image(customer_id: str) -> Response:
    """
    Get restored image for a customer.
    
    Args:
        customer_id: Customer ID
    
    Returns:
        Image binary data
    """
    # Try Supabase first
    if supabase_storage:
        supabase_url = supabase_storage.get_image_url(customer_id, "restored")
        if supabase_url:
            # Redirect to Supabase URL
            from fastapi.responses import RedirectResponse
            return RedirectResponse(url=supabase_url)
    
    # Fallback to local storage
    image_data = local_storage.get_image_binary(customer_id, "restored")
    if image_data:
        return Response(content=image_data, media_type="image/png")
    
    raise HTTPException(status_code=404, detail="Restored image not found")


@router.get("/{customer_id}/metadata")
async def get_image_metadata(customer_id: str, include_base64: bool = False) -> dict:
    """
    Get metadata for both original and restored images.
    
    Args:
        customer_id: Customer ID
        include_base64: Whether to include Base64 encoded images
    
    Returns:
        Metadata dict with URLs for both images
    """
    original_metadata = local_storage.get_image(customer_id, "original")
    restored_metadata = local_storage.get_image(customer_id, "restored")
    
    # Get Supabase URLs if available
    original_url = None
    restored_url = None
    
    if supabase_storage:
        original_url = supabase_storage.get_image_url(customer_id, "original")
        restored_url = supabase_storage.get_image_url(customer_id, "restored")
    
    # Get Base64 if requested
    original_base64 = None
    restored_base64 = None
    
    if include_base64:
        try:
            from src.config.config_manager import ConfigManager
            config = ConfigManager()
            max_size = config.get("image_storage", {}).get("base64", {}).get("max_size_bytes", 1048576)
            original_base64 = local_storage.get_image_base64(customer_id, "original", max_size)
            restored_base64 = local_storage.get_image_base64(customer_id, "restored", max_size)
        except Exception as e:
            log.warning(f"Failed to get Base64 images: {e}")
    
    return {
        "customer_id": customer_id,
        "original": {
            "metadata": original_metadata,
            "url": original_url,
            "local_url": f"/v1/images/{customer_id}/original" if original_metadata else None,
            "base64": original_base64
        },
        "restored": {
            "metadata": restored_metadata,
            "url": restored_url,
            "local_url": f"/v1/images/{customer_id}/restored" if restored_metadata else None,
            "base64": restored_base64
        }
    }
