"""
Embeddle Security Module

Centralized security utilities for authentication, authorization,
input validation, and rate limiting.

This module is the single source of truth for all security-related
functionality. Other modules should import from here rather than
implementing their own security measures.
"""

from .rate_limiter import (
    RateLimitConfig,
    RateLimiter,
    RateLimitResult,
    check_rate_limit_strict,
    get_rate_limiter,
    check_embedding_rate_limit,
    get_combined_identifier,
)
from .validators import (
    Validators,
    ValidationResult,
    # Game code
    sanitize_game_code,
    # Player ID
    sanitize_player_id,
    sanitize_player_id_strict,
    sanitize_ai_player_id,
    is_ai_player_id,
    # Player name
    sanitize_player_name,
    # Username
    validate_username,
    sanitize_username,
    # Word
    sanitize_word,
    # Chat
    sanitize_chat_message,
    # Email
    sanitize_email,
    # Cosmetic
    sanitize_cosmetic_id,
    # Theme
    sanitize_theme_name,
    # Visibility
    sanitize_visibility,
    # Request validation
    validate_request_body_size,
    get_request_size_limit,
    REQUEST_SIZE_LIMITS,
    # Utilities
    hash_for_lookup,
    is_reserved_name,
)
from .auth import (
    require_auth,
    require_admin,
    get_current_user,
    create_jwt_token,
    verify_jwt_token,
    refresh_jwt_token,
    revoke_token,
    is_token_revoked,
    generate_oauth_state,
    constant_time_compare,
    AuthenticatedUser,
)
from .env_validator import (
    validate_required_env_vars,
    get_env_status,
    print_env_status,
)
from .monitoring import (
    SecurityMonitor,
    SecurityEvent,
    SecurityEventType,
    get_security_monitor,
    log_security_event,
    log_auth_success,
    log_auth_failure,
    log_rate_limit_hit,
    log_rate_limit_blocked,
    log_webhook_event,
    log_admin_action,
    log_suspicious_input,
)

__all__ = [
    # Rate limiting
    'RateLimitConfig',
    'RateLimiter',
    'RateLimitResult',
    'check_rate_limit_strict',
    'get_rate_limiter',
    'check_embedding_rate_limit',
    'get_combined_identifier',
    # Validators
    'Validators',
    'ValidationResult',
    'sanitize_game_code',
    'sanitize_player_id',
    'sanitize_player_id_strict',
    'sanitize_ai_player_id',
    'is_ai_player_id',
    'sanitize_player_name',
    'validate_username',
    'sanitize_username',
    'sanitize_word',
    'sanitize_chat_message',
    'sanitize_email',
    'sanitize_cosmetic_id',
    'sanitize_theme_name',
    'sanitize_visibility',
    'validate_request_body_size',
    'get_request_size_limit',
    'REQUEST_SIZE_LIMITS',
    'hash_for_lookup',
    'is_reserved_name',
    # Auth
    'require_auth',
    'require_admin',
    'get_current_user',
    'create_jwt_token',
    'verify_jwt_token',
    'refresh_jwt_token',
    'revoke_token',
    'is_token_revoked',
    'generate_oauth_state',
    'constant_time_compare',
    'AuthenticatedUser',
    # Environment
    'validate_required_env_vars',
    'get_env_status',
    'print_env_status',
    # Monitoring
    'SecurityMonitor',
    'SecurityEvent',
    'SecurityEventType',
    'get_security_monitor',
    'log_security_event',
    'log_auth_success',
    'log_auth_failure',
    'log_rate_limit_hit',
    'log_rate_limit_blocked',
    'log_webhook_event',
    'log_admin_action',
    'log_suspicious_input',
]

