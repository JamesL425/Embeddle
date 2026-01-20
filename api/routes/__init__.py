"""
Routes Module
Modular route handlers for the API

This module provides centralized routing for all API endpoints:
- games: Game CRUD and gameplay actions
- auth: OAuth authentication and session management
- users: User profiles, cosmetics, and daily ops
- leaderboard: Casual and ranked leaderboards
- singleplayer: Singleplayer game and AI management
- admin: Administrative endpoints
"""

from .games import handle_games_routes
from .users import handle_users_routes
from .leaderboard import handle_leaderboard_routes
from .singleplayer import handle_singleplayer_routes
from .admin import handle_admin_routes, is_admin_user

# Auth routes need special handling for redirects
from .auth import (
    handle_auth_routes,
    verify_user_jwt,
    create_user_jwt,
    generate_oauth_state,
    validate_oauth_state,
)

__all__ = [
    # Route handlers
    "handle_games_routes",
    "handle_auth_routes",
    "handle_users_routes",
    "handle_leaderboard_routes",
    "handle_singleplayer_routes",
    "handle_admin_routes",
    # Auth helpers
    "verify_user_jwt",
    "create_user_jwt",
    "generate_oauth_state",
    "validate_oauth_state",
    # Admin helpers
    "is_admin_user",
]

