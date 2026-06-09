"""
Supabase storage integration for images.
"""
import logging
import os
from pathlib import Path
from typing import Optional

try:
    from supabase import create_client, Client
    from supabase.lib.storage_api import StorageAPI
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    Client = None
    StorageAPI = None

log = logging.getLogger(__name__)


class SupabaseImageStorage:
    """Supabase storage for images."""
    
    def __init__(
        self,
        supabase_url: Optional[str] = None,
        supabase_key: Optional[str] = None,
        bucket_name: Optional[str] = None
    ):
        if not SUPABASE_AVAILABLE:
            raise ImportError(
                "supabase library is not installed. "
                "Install it with: pip install supabase"
            )
        
        # Try to get from config if not provided
        if supabase_url is None or supabase_key is None:
            try:
                from src.config.config_manager import ConfigManager
                config = ConfigManager()
                image_storage_config = config.get("image_storage", {}).get("supabase", {})
                
                if supabase_url is None:
                    supabase_url = image_storage_config.get("url") or os.getenv("SUPABASE_URL")
                if supabase_key is None:
                    supabase_key = image_storage_config.get("key") or os.getenv("SUPABASE_KEY")
                if bucket_name is None:
                    bucket_name = image_storage_config.get("bucket", "skin-analysis-images")
                
                # Check if Supabase is enabled
                if not image_storage_config.get("enabled", False):
                    log.warning("Supabase image storage is disabled in config")
                    raise ValueError("Supabase image storage is disabled")
                    
            except Exception as e:
                log.warning(f"Failed to get Supabase config: {e}")
        
        if not supabase_url or not supabase_key:
            raise ValueError("Supabase URL and key are required")
        
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key
        self.bucket_name = bucket_name or "skin-analysis-images"
        self.client: Optional[Client] = None
        self.storage: Optional[StorageAPI] = None
        self._init_client()
    
    def _init_client(self) -> None:
        """Initialize Supabase client."""
        try:
            self.client = create_client(
                self.supabase_url,
                self.supabase_key
            )
            self.storage = self.client.storage
            log.info("Supabase client initialized successfully")
        except Exception as e:
            log.error(f"Failed to initialize Supabase client: {e}")
            raise
    
    def upload_image(
        self,
        customer_id: str,
        image_type: str,
        file_path: Path
    ) -> Optional[str]:
        """
        Upload image to Supabase storage.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
            file_path: Path to the image file
        
        Returns:
            Public URL of the uploaded image or None
        """
        if not file_path.exists():
            log.error(f"Image file not found: {file_path}")
            return None
        
        if not self.client or not self.storage:
            log.error("Supabase client not initialized")
            return None
        
        try:
            # Generate unique filename
            file_extension = file_path.suffix
            filename = f"{customer_id}_{image_type}{file_extension}"
            storage_path = f"{customer_id}/{filename}"
            
            # Upload file
            with open(file_path, 'rb') as f:
                file_data = f.read()
            
            self.storage.from_(self.bucket_name).upload(
                path=storage_path,
                file=file_data,
                file_options={
                    "content-type": "image/png",
                    "upsert": "true"
                }
            )
            
            # Get public URL
            public_url = self.storage.from_(self.bucket_name).get_public_url(storage_path)
            log.info(f"Image uploaded to Supabase: {public_url}")
            return public_url
            
        except Exception as e:
            log.error(f"Failed to upload image to Supabase: {e}")
            return None
    
    def get_image_url(
        self,
        customer_id: str,
        image_type: str
    ) -> Optional[str]:
        """
        Get public URL of an image from Supabase storage.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
        
        Returns:
            Public URL or None
        """
        if not self.client or not self.storage:
            log.error("Supabase client not initialized")
            return None
        
        try:
            # Try to find the file
            files = self.storage.from_(self.bucket_name).list(path=customer_id)
            
            for file in files:
                if f"{customer_id}_{image_type}" in file['name']:
                    storage_path = f"{customer_id}/{file['name']}"
                    return self.storage.from_(self.bucket_name).get_public_url(storage_path)
            
            log.warning(f"Image not found in Supabase: {customer_id}/{image_type}")
            return None
            
        except Exception as e:
            log.error(f"Failed to get image URL from Supabase: {e}")
            return None
    
    def delete_image(
        self,
        customer_id: str,
        image_type: str
    ) -> bool:
        """
        Delete image from Supabase storage.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
        
        Returns:
            True if deleted, False otherwise
        """
        if not self.client or not self.storage:
            log.error("Supabase client not initialized")
            return False
        
        try:
            # Try to find and delete the file
            files = self.storage.from_(self.bucket_name).list(path=customer_id)
            
            for file in files:
                if f"{customer_id}_{image_type}" in file['name']:
                    storage_path = f"{customer_id}/{file['name']}"
                    self.storage.from_(self.bucket_name).remove([storage_path])
                    log.info(f"Image deleted from Supabase: {storage_path}")
                    return True
            
            log.warning(f"Image not found in Supabase: {customer_id}/{image_type}")
            return False
            
        except Exception as e:
            log.error(f"Failed to delete image from Supabase: {e}")
            return False
