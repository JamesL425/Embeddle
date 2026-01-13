"""
Embeddle Security Module

Centralized security utilities for authentication, authorization,
input validation, and rate limiting.
"""

from .rate_limiter import (
    RateLimitConfig,
    RateLimiter,
    check_rate_limit_strict,
    get_rate_limiter,
)
from .validators import (
    Validators,
    sanitize_game_code,
    sanitize_player_id,
    sanitize_player_name,
    sanitize_word,
    sanitize_chat_message,
    validate_request_body_size,
)
from .auth import (
    require_auth,
    require_admin,
    get_current_user,
    create_jwt_token,
    verify_jwt_token,
    revoke_token,
    is_token_revoked,
)
from .env_validator import validate_required_env_vars
from .monitoring import SecurityMonitor, log_security_event

__all__ = [
    # Rate limiting
    'RateLimitConfig',
    'RateLimiter', 
    'check_rate_limit_strict',
    'get_rate_limiter',
    # Validators
    'Validators',
    'sanitize_game_code',
    'sanitize_player_id',
    'sanitize_player_name',
    'sanitize_word',
    'sanitize_chat_message',
    'validate_request_body_size',
    # Auth
    'require_auth',
    'require_admin',
    'get_current_user',
    'create_jwt_token',
    'verify_jwt_token',
    'revoke_token',
    'is_token_revoked',
    # Environment
    'validate_required_env_vars',
    # Monitoring
    'SecurityMonitor',
    'log_security_event',
]

