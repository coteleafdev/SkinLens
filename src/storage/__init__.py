"""
Storage module for image storage (local DB and Supabase).
"""
from .local_db import LocalImageStorage
from .supabase_storage import SupabaseImageStorage

__all__ = ["LocalImageStorage", "SupabaseImageStorage"]
