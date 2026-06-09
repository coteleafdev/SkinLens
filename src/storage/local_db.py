"""
Local SQLite DB storage for images.
"""
import sqlite3
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
import hashlib

log = logging.getLogger(__name__)


class LocalImageStorage:
    """Local SQLite DB storage for images."""
    
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            # Try to get from config
            try:
                from src.config.config_manager import ConfigManager
                config = ConfigManager()
                db_path_str = config.get("image_storage", {}).get("local_db", {}).get("path", "data/images.db")
                # Override with environment variable if set
                db_path_str = os.getenv("IMAGE_DB", db_path_str)
                db_path = Path(db_path_str)
            except Exception as e:
                log.warning(f"Failed to get DB path from config: {e}, using default")
                db_path = Path("data/images.db")
        
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
    
    def _init_db(self) -> None:
        """Initialize the database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    customer_id TEXT NOT NULL,
                    image_type TEXT NOT NULL,  -- 'original' or 'restored'
                    file_path TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(customer_id, image_type)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_customer_id 
                ON images(customer_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_image_type 
                ON images(image_type)
            """)
            conn.commit()
    
    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of the file."""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def store_image(
        self,
        customer_id: str,
        image_type: str,
        file_path: Path
    ) -> int:
        """
        Store image metadata in local DB.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
            file_path: Path to the image file
        
        Returns:
            Image ID
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")
        
        file_hash = self._calculate_hash(file_path)
        file_size = file_path.stat().st_size
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO images 
                (customer_id, image_type, file_path, file_hash, file_size)
                VALUES (?, ?, ?, ?, ?)
            """, (customer_id, image_type, str(file_path), file_hash, file_size))
            conn.commit()
            return cursor.lastrowid
    
    def get_image(
        self,
        customer_id: str,
        image_type: str
    ) -> Optional[dict]:
        """
        Get image metadata from local DB.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
        
        Returns:
            Image metadata dict or None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM images 
                WHERE customer_id = ? AND image_type = ?
            """, (customer_id, image_type))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    
    def get_image_binary(
        self,
        customer_id: str,
        image_type: str
    ) -> Optional[bytes]:
        """
        Get image binary data from local file system.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
        
        Returns:
            Image binary data or None
        """
        metadata = self.get_image(customer_id, image_type)
        if metadata:
            file_path = Path(metadata['file_path'])
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    return f.read()
        return None
    
    def delete_image(
        self,
        customer_id: str,
        image_type: str
    ) -> bool:
        """
        Delete image metadata from local DB.
        
        Args:
            customer_id: Customer ID
            image_type: 'original' or 'restored'
        
        Returns:
            True if deleted, False otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM images 
                WHERE customer_id = ? AND image_type = ?
            """, (customer_id, image_type))
            conn.commit()
            return cursor.rowcount > 0
    
    def list_customer_images(self, customer_id: str) -> list[dict]:
        """
        List all images for a customer.
        
        Args:
            customer_id: Customer ID
        
        Returns:
            List of image metadata dicts
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM images 
                WHERE customer_id = ?
                ORDER BY created_at DESC
            """, (customer_id,))
            return [dict(row) for row in cursor.fetchall()]
