"""
Centralized Rate Limiting Module

Provides fail-closed rate limiting with:
- IP-based and user-based combined limiting
- Exponential backoff for repeat offenders
- Separate limits for authenticated vs anonymous users
- OpenAI embedding cost protection
"""

import os
import time
import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple, Dict, Any
from functools import lru_cache


class RateLimitResult(Enum):
    """Result of a rate limit check."""
    ALLOWED = "allowed"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"  # For repeat offenders


@dataclass
class RateLimitConfig:
    """Configuration for rate limit tiers."""
    
    # General API requests (per IP)
    GENERAL = {"max_requests": 60, "window_seconds": 60, "prefix": "ratelimit:general"}
    
    # Game creation (per IP) - reduced from 5 to prevent lobby spam
    GAME_CREATE = {"max_requests": 3, "window_seconds": 60, "prefix": "ratelimit:create"}
    
    # Join requests (per IP)
    JOIN = {"max_requests": 10, "window_seconds": 60, "prefix": "ratelimit:join"}
    
    # Guess submissions (per player per game)
    GUESS = {"max_requests": 30, "window_seconds": 60, "prefix": "ratelimit:guess"}
    
    # Chat messages (per player) - reduced from 20
    CHAT = {"max_requests": 15, "window_seconds": 60, "prefix": "ratelimit:chat"}
    
    # OpenAI embedding calls (per user) - NEW: Protect API costs
    EMBEDDING = {"max_requests": 20, "window_seconds": 60, "prefix": "ratelimit:embedding"}
    
    # Daily embedding quota (per authenticated user)
    EMBEDDING_DAILY = {"max_requests": 500, "window_seconds": 86400, "prefix": "ratelimit:embedding_daily"}
    
    # Auth attempts (per IP) - Prevent brute force
    AUTH = {"max_requests": 10, "window_seconds": 300, "prefix": "ratelimit:auth"}
    
    # Webhook requests (per IP)
    WEBHOOK = {"max_requests": 30, "window_seconds": 60, "prefix": "ratelimit:webhook"}


# Lazy-initialized Redis client reference
_redis_client = None


def _get_redis():
    """Get Redis client (lazy initialization to avoid circular imports)."""
    global _redis_client
    if _redis_client is None:
        try:
            from upstash_redis import Redis
            _redis_client = Redis(
                url=os.getenv("UPSTASH_REDIS_REST_URL"),
                token=os.getenv("UPSTASH_REDIS_REST_TOKEN"),
            )
        except Exception as e:
            print(f"[SECURITY] Failed to initialize Redis for rate limiting: {e}")
            return None
    return _redis_client


class RateLimiter:
    """
    Centralized rate limiter with fail-closed behavior.
    
    Unlike the default upstash-ratelimit which fails open,
    this implementation fails closed for security-critical endpoints.
    """
    
    def __init__(
        self,
        max_requests: int,
        window_seconds: int,
        prefix: str = "ratelimit",
        fail_closed: bool = True,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.prefix = prefix
        self.fail_closed = fail_closed
    
    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for rate limit tracking."""
        # Hash long identifiers to keep keys manageable
        if len(identifier) > 64:
            identifier = hashlib.sha256(identifier.encode()).hexdigest()[:16]
        return f"{self.prefix}:{identifier}"
    
    def check(self, identifier: str) -> Tuple[RateLimitResult, Dict[str, Any]]:
        """
        Check if request is allowed under rate limit.
        
        Returns:
            Tuple of (result, metadata) where metadata includes:
            - remaining: requests remaining in window
            - reset_at: timestamp when window resets
            - blocked_until: timestamp if blocked (for repeat offenders)
        """
        redis = _get_redis()
        
        if redis is None:
            # Redis unavailable - fail closed or open based on config
            if self.fail_closed:
                return RateLimitResult.RATE_LIMITED, {
                    "remaining": 0,
                    "reset_at": int(time.time()) + self.window_seconds,
                    "error": "rate_limit_unavailable",
                }
            else:
                return RateLimitResult.ALLOWED, {
                    "remaining": self.max_requests,
                    "reset_at": int(time.time()) + self.window_seconds,
                }
        
        try:
            key = self._get_key(identifier)
            block_key = f"{key}:blocked"
            now = int(time.time())
            window_start = now - self.window_seconds
            
            # Check if identifier is blocked (repeat offender)
            blocked_until = redis.get(block_key)
            if blocked_until:
                try:
                    blocked_until = int(blocked_until)
                    if blocked_until > now:
                        return RateLimitResult.BLOCKED, {
                            "remaining": 0,
                            "reset_at": blocked_until,
                            "blocked_until": blocked_until,
                        }
                except (ValueError, TypeError):
                    pass
            
            # Use sorted set for sliding window rate limiting
            pipe_result = None
            try:
                # Remove old entries and count current
                redis.zremrangebyscore(key, 0, window_start)
                count = redis.zcard(key)
                
                if count is None:
                    count = 0
                    
            except Exception as e:
                print(f"[SECURITY] Rate limit Redis error: {e}")
                if self.fail_closed:
                    return RateLimitResult.RATE_LIMITED, {
                        "remaining": 0,
                        "reset_at": now + self.window_seconds,
                        "error": str(e),
                    }
                return RateLimitResult.ALLOWED, {"remaining": self.max_requests, "reset_at": now + self.window_seconds}
            
            remaining = max(0, self.max_requests - count)
            reset_at = now + self.window_seconds
            
            if count >= self.max_requests:
                # Check for repeat offender pattern (3+ rate limits in short period)
                violation_key = f"{key}:violations"
                try:
                    violations = redis.incr(violation_key)
                    redis.expire(violation_key, 3600)  # Track violations for 1 hour
                    
                    if violations and int(violations) >= 3:
                        # Block repeat offender with exponential backoff
                        block_duration = min(3600, 60 * (2 ** (int(violations) - 3)))
                        blocked_until = now + block_duration
                        redis.setex(block_key, block_duration, str(blocked_until))
                        
                        return RateLimitResult.BLOCKED, {
                            "remaining": 0,
                            "reset_at": blocked_until,
                            "blocked_until": blocked_until,
                            "violations": int(violations),
                        }
                except Exception:
                    pass
                
                return RateLimitResult.RATE_LIMITED, {
                    "remaining": 0,
                    "reset_at": reset_at,
                }
            
            # Add current request to window
            try:
                redis.zadd(key, {f"{now}:{id(self)}": now})
                redis.expire(key, self.window_seconds + 1)
            except Exception as e:
                print(f"[SECURITY] Rate limit tracking error: {e}")
            
            return RateLimitResult.ALLOWED, {
                "remaining": remaining - 1,
                "reset_at": reset_at,
            }
            
        except Exception as e:
            print(f"[SECURITY] Rate limit check failed: {e}")
            if self.fail_closed:
                return RateLimitResult.RATE_LIMITED, {
                    "remaining": 0,
                    "reset_at": int(time.time()) + self.window_seconds,
                    "error": str(e),
                }
            return RateLimitResult.ALLOWED, {
                "remaining": self.max_requests,
                "reset_at": int(time.time()) + self.window_seconds,
            }


# Cached rate limiter instances
_rate_limiters: Dict[str, RateLimiter] = {}


def get_rate_limiter(config_name: str, fail_closed: bool = True) -> RateLimiter:
    """
    Get or create a rate limiter for the given configuration.
    
    Args:
        config_name: Name of config from RateLimitConfig (e.g., "GENERAL", "EMBEDDING")
        fail_closed: Whether to deny requests when Redis is unavailable
    
    Returns:
        RateLimiter instance
    """
    cache_key = f"{config_name}:{fail_closed}"
    
    if cache_key not in _rate_limiters:
        config = getattr(RateLimitConfig, config_name, None)
        if config is None:
            raise ValueError(f"Unknown rate limit config: {config_name}")
        
        _rate_limiters[cache_key] = RateLimiter(
            max_requests=config["max_requests"],
            window_seconds=config["window_seconds"],
            prefix=config["prefix"],
            fail_closed=fail_closed,
        )
    
    return _rate_limiters[cache_key]


def check_rate_limit_strict(
    config_name: str,
    identifier: str,
    fail_closed: bool = True,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Check rate limit with strict (fail-closed) behavior.
    
    Args:
        config_name: Name of config from RateLimitConfig
        identifier: Unique identifier (IP, user ID, etc.)
        fail_closed: Whether to deny when Redis unavailable
    
    Returns:
        Tuple of (is_allowed, metadata)
    """
    limiter = get_rate_limiter(config_name, fail_closed)
    result, metadata = limiter.check(identifier)
    
    is_allowed = result == RateLimitResult.ALLOWED
    metadata["result"] = result.value
    
    return is_allowed, metadata


def get_combined_identifier(ip: str, user_id: Optional[str] = None) -> str:
    """
    Create combined identifier for IP + user rate limiting.
    
    This allows stricter per-user limits while maintaining IP limits.
    """
    if user_id:
        return f"{ip}:{user_id}"
    return ip


def check_embedding_rate_limit(ip: str, user_id: Optional[str] = None) -> Tuple[bool, str]:
    """
    Special rate limit check for OpenAI embedding calls.
    
    Combines per-request and daily quotas to protect API costs.
    
    Returns:
        Tuple of (is_allowed, error_message)
    """
    identifier = get_combined_identifier(ip, user_id)
    
    # Check per-minute limit
    allowed, meta = check_rate_limit_strict("EMBEDDING", identifier, fail_closed=True)
    if not allowed:
        if meta.get("result") == "blocked":
            return False, "Too many requests. You are temporarily blocked."
        return False, f"Embedding rate limit exceeded. Try again in {meta.get('reset_at', 0) - int(time.time())} seconds."
    
    # Check daily quota for authenticated users
    if user_id:
        allowed, meta = check_rate_limit_strict("EMBEDDING_DAILY", user_id, fail_closed=True)
        if not allowed:
            return False, "Daily embedding quota exceeded. Try again tomorrow."
    
    return True, ""

