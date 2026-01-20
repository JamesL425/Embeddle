"""
Redis Client Module
Centralized Redis connection management

This module provides a singleton Redis client for all data operations.
It handles connection initialization and provides helper functions
for checking Redis configuration status.
"""

import os
from typing import Optional, Any

# Type alias for Redis client (actual type depends on upstash_redis)
RedisClient = Any

# Lazy-initialized Redis client
_redis_client: Optional[RedisClient] = None


def get_redis() -> Optional[RedisClient]:
    """
    Get Redis client singleton.
    
    Returns:
        Redis client instance, or None if initialization failed.
        
    Note:
        The client is lazily initialized on first call.
        Subsequent calls return the same instance.
    """
    global _redis_client
    if _redis_client is None:
        try:
            from upstash_redis import Redis
            _redis_client = Redis(
                url=os.getenv("UPSTASH_REDIS_REST_URL"),
                token=os.getenv("UPSTASH_REDIS_REST_TOKEN"),
            )
        except Exception as e:
            print(f"[DATA] Failed to initialize Redis: {e}")
            return None
    return _redis_client


def get_redis_url() -> Optional[str]:
    """
    Get Redis URL from environment.
    
    Returns:
        Redis REST API URL, or None if not configured.
    """
    return os.getenv("UPSTASH_REDIS_REST_URL")


def get_redis_token() -> Optional[str]:
    """
    Get Redis token from environment.
    
    Returns:
        Redis REST API token, or None if not configured.
    """
    return os.getenv("UPSTASH_REDIS_REST_TOKEN")


def is_redis_configured() -> bool:
    """
    Check if Redis is properly configured.
    
    Returns:
        True if both URL and token are set.
    """
    return bool(get_redis_url() and get_redis_token())

