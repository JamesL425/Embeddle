"""
Admin Routes
Administrative endpoints for game management and monitoring

This module handles:
- Admin authentication and authorization
- Security event viewing
- User management
- Game moderation
- System status
"""

import os
import json
from typing import Tuple, Any, Optional, Dict, List

from ..data.redis_client import get_redis
from ..data.user_repository import get_user_by_id, save_user

# Try to import security modules
try:
    from ..security.auth import verify_jwt_token
    from ..security.monitoring import (
        get_security_monitor,
        SecurityEventType,
        log_admin_action,
    )
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False
    
    def verify_jwt_token(token: str) -> Optional[dict]:
        return None
    
    def log_admin_action(*args, **kwargs):
        pass


# ============== CONFIGURATION ==============

def _get_admin_emails() -> List[str]:
    """Get list of admin email addresses."""
    admin_emails = os.getenv('ADMIN_EMAILS', '')
    return [e.strip().lower() for e in admin_emails.split(',') if e.strip()]


def is_admin_user(headers: Dict[str, str]) -> bool:
    """
    Check if request is from an admin user.
    
    Args:
        headers: Request headers
        
    Returns:
        True if user is admin
    """
    auth_header = headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False
    
    token = auth_header[7:]
    payload = verify_jwt_token(token)
    
    if not payload:
        return False
    
    email = str(payload.get('email', '')).strip().lower()
    if not email:
        return False
    
    return email in _get_admin_emails()


def get_admin_user_id(headers: Dict[str, str]) -> Optional[str]:
    """Get admin user ID from headers."""
    auth_header = headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None
    
    token = auth_header[7:]
    payload = verify_jwt_token(token)
    
    if not payload:
        return None
    
    email = str(payload.get('email', '')).strip().lower()
    if email not in _get_admin_emails():
        return None
    
    return payload.get('sub')


# ============== ROUTE HANDLERS ==============

def handle_admin_routes(
    handler,
    method: str,
    path: str,
    body: Dict[str, Any],
    headers: Dict[str, str],
    client_ip: str,
) -> Optional[Tuple[int, Any]]:
    """
    Route handler for admin endpoints.
    
    Args:
        handler: HTTP request handler instance
        method: HTTP method
        path: Request path
        body: Request body
        headers: Request headers
        client_ip: Client IP address
        
    Returns:
        Tuple of (status_code, response_body) or None if not handled
    """
    
    # All admin routes require authentication
    if not path.startswith('/api/admin'):
        return None
    
    # Check admin authorization
    if not is_admin_user(headers):
        return 403, {"detail": "Admin access required"}
    
    admin_user_id = get_admin_user_id(headers)
    
    # GET /api/admin/status - System status
    if path == '/api/admin/status' and method == 'GET':
        return _handle_system_status()
    
    # GET /api/admin/security-events - Security event log
    if path == '/api/admin/security-events' and method == 'GET':
        return _handle_security_events()
    
    # GET /api/admin/security-alerts - Security alerts
    if path == '/api/admin/security-alerts' and method == 'GET':
        return _handle_security_alerts()
    
    # GET /api/admin/users - List users
    if path == '/api/admin/users' and method == 'GET':
        return _handle_list_users()
    
    # GET /api/admin/user/{id} - Get user details
    if path.startswith('/api/admin/user/') and method == 'GET':
        user_id = path.split('/')[-1]
        return _handle_get_user(user_id)
    
    # POST /api/admin/user/{id}/grant-credits - Grant credits to user
    if path.startswith('/api/admin/user/') and path.endswith('/grant-credits') and method == 'POST':
        parts = path.split('/')
        user_id = parts[-2]
        return _handle_grant_credits(user_id, body, admin_user_id, client_ip)
    
    # POST /api/admin/user/{id}/set-donor - Set donor status
    if path.startswith('/api/admin/user/') and path.endswith('/set-donor') and method == 'POST':
        parts = path.split('/')
        user_id = parts[-2]
        return _handle_set_donor(user_id, body, admin_user_id, client_ip)
    
    # GET /api/admin/games - List active games
    if path == '/api/admin/games' and method == 'GET':
        return _handle_list_games()
    
    # POST /api/admin/game/{code}/end - Force end a game
    if path.startswith('/api/admin/game/') and path.endswith('/end') and method == 'POST':
        parts = path.split('/')
        code = parts[-2].upper()
        return _handle_end_game(code, admin_user_id, client_ip)
    
    # GET /api/admin/env-status - Environment variable status
    if path == '/api/admin/env-status' and method == 'GET':
        return _handle_env_status()
    
    return None  # Not handled


# ============== HANDLER IMPLEMENTATIONS ==============

def _handle_system_status() -> Tuple[int, Any]:
    """Get system status information."""
    redis = get_redis()
    
    status = {
        "redis_connected": redis is not None,
        "environment": os.getenv('VERCEL_ENV', 'development'),
        "security_modules": _SECURITY_AVAILABLE,
    }
    
    if redis:
        try:
            # Get some basic stats
            info = redis.info()
            status["redis_info"] = {
                "connected_clients": info.get("connected_clients"),
                "used_memory_human": info.get("used_memory_human"),
            }
        except Exception:
            pass
        
        try:
            # Count active games
            cursor = 0
            game_count = 0
            while True:
                cursor, keys = redis.scan(cursor, match="game:*", count=100)
                game_count += len(keys)
                if cursor == 0:
                    break
            status["active_games"] = game_count
        except Exception:
            pass
    
    return 200, status


def _handle_security_events() -> Tuple[int, Any]:
    """Get recent security events."""
    if not _SECURITY_AVAILABLE:
        return 200, {"events": [], "message": "Security modules not available"}
    
    try:
        monitor = get_security_monitor()
        events = monitor.get_recent_events(limit=100)
        return 200, {"events": events}
    except Exception as e:
        return 500, {"detail": str(e)}


def _handle_security_alerts() -> Tuple[int, Any]:
    """Get recent security alerts."""
    if not _SECURITY_AVAILABLE:
        return 200, {"alerts": [], "message": "Security modules not available"}
    
    try:
        monitor = get_security_monitor()
        alerts = monitor.get_alerts(limit=50)
        return 200, {"alerts": alerts}
    except Exception as e:
        return 500, {"detail": str(e)}


def _handle_list_users() -> Tuple[int, Any]:
    """List recent users (limited)."""
    redis = get_redis()
    if not redis:
        return 500, {"detail": "Redis not available"}
    
    try:
        users = []
        cursor = 0
        count = 0
        max_users = 100
        
        while count < max_users:
            cursor, keys = redis.scan(cursor, match="user:*", count=50)
            for key in keys:
                if count >= max_users:
                    break
                try:
                    data = redis.get(key)
                    if data:
                        user = json.loads(data)
                        users.append({
                            "id": user.get("id"),
                            "name": user.get("name"),
                            "email": user.get("email"),
                            "is_donor": user.get("is_donor", False),
                            "created_at": user.get("created_at"),
                        })
                        count += 1
                except Exception:
                    continue
            
            if cursor == 0:
                break
        
        return 200, {"users": users, "count": len(users)}
    except Exception as e:
        return 500, {"detail": str(e)}


def _handle_get_user(user_id: str) -> Tuple[int, Any]:
    """Get detailed user information."""
    user = get_user_by_id(user_id)
    if not user:
        return 404, {"detail": "User not found"}
    
    return 200, {
        "id": user.get("id"),
        "name": user.get("name"),
        "email": user.get("email"),
        "avatar": user.get("avatar"),
        "is_donor": user.get("is_donor", False),
        "created_at": user.get("created_at"),
        "last_login": user.get("last_login"),
        "stats": user.get("stats", {}),
        "wallet": user.get("wallet", {}),
        "streak": user.get("streak", {}),
        "cosmetics": user.get("cosmetics", {}),
        "owned_cosmetics": user.get("owned_cosmetics", {}),
    }


def _handle_grant_credits(
    user_id: str,
    body: Dict[str, Any],
    admin_user_id: str,
    client_ip: str
) -> Tuple[int, Any]:
    """Grant credits to a user."""
    user = get_user_by_id(user_id)
    if not user:
        return 404, {"detail": "User not found"}
    
    amount = body.get("amount", 0)
    try:
        amount = int(amount)
    except (ValueError, TypeError):
        return 400, {"detail": "Invalid amount"}
    
    if amount <= 0:
        return 400, {"detail": "Amount must be positive"}
    
    if amount > 100000:
        return 400, {"detail": "Amount too large"}
    
    # Grant credits
    if "wallet" not in user:
        user["wallet"] = {"credits": 0}
    
    current = user["wallet"].get("credits", 0)
    user["wallet"]["credits"] = current + amount
    
    save_user(user)
    
    # Log admin action
    log_admin_action(client_ip, admin_user_id, "grant_credits", {
        "target_user": user_id,
        "amount": amount,
    })
    
    return 200, {
        "ok": True,
        "new_balance": user["wallet"]["credits"],
    }


def _handle_set_donor(
    user_id: str,
    body: Dict[str, Any],
    admin_user_id: str,
    client_ip: str
) -> Tuple[int, Any]:
    """Set donor status for a user."""
    user = get_user_by_id(user_id)
    if not user:
        return 404, {"detail": "User not found"}
    
    is_donor = body.get("is_donor", False)
    if not isinstance(is_donor, bool):
        is_donor = str(is_donor).lower() in ('true', '1', 'yes')
    
    user["is_donor"] = is_donor
    save_user(user)
    
    # Log admin action
    log_admin_action(client_ip, admin_user_id, "set_donor", {
        "target_user": user_id,
        "is_donor": is_donor,
    })
    
    return 200, {"ok": True, "is_donor": is_donor}


def _handle_list_games() -> Tuple[int, Any]:
    """List active games."""
    redis = get_redis()
    if not redis:
        return 500, {"detail": "Redis not available"}
    
    try:
        games = []
        cursor = 0
        
        while True:
            cursor, keys = redis.scan(cursor, match="game:*", count=100)
            for key in keys:
                try:
                    data = redis.get(key)
                    if data:
                        game = json.loads(data)
                        games.append({
                            "code": game.get("code"),
                            "status": game.get("status"),
                            "player_count": len(game.get("players", [])),
                            "is_ranked": game.get("is_ranked", False),
                            "is_singleplayer": game.get("is_singleplayer", False),
                            "visibility": game.get("visibility"),
                            "created_at": game.get("created_at"),
                        })
                except Exception:
                    continue
            
            if cursor == 0:
                break
        
        # Sort by creation time (newest first)
        games.sort(key=lambda g: g.get("created_at", 0), reverse=True)
        
        return 200, {"games": games[:100], "total": len(games)}
    except Exception as e:
        return 500, {"detail": str(e)}


def _handle_end_game(
    code: str,
    admin_user_id: str,
    client_ip: str
) -> Tuple[int, Any]:
    """Force end a game."""
    from ..data.game_repository import load_game, save_game, delete_game
    
    game = load_game(code)
    if not game:
        return 404, {"detail": "Game not found"}
    
    # Mark game as finished
    game["status"] = "finished"
    game["ended_by_admin"] = True
    save_game(code, game)
    
    # Log admin action
    log_admin_action(client_ip, admin_user_id, "end_game", {
        "game_code": code,
    })
    
    return 200, {"ok": True, "code": code}


def _handle_env_status() -> Tuple[int, Any]:
    """Get environment variable status (without values)."""
    required_vars = [
        "OPENAI_API_KEY",
        "UPSTASH_REDIS_REST_URL",
        "UPSTASH_REDIS_REST_TOKEN",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "JWT_SECRET",
    ]
    
    optional_vars = [
        "KOFI_VERIFICATION_TOKEN",
        "ADMIN_EMAILS",
        "SITE_URL",
        "OAUTH_REDIRECT_URI",
    ]
    
    status = {}
    
    for var in required_vars:
        value = os.getenv(var)
        status[var] = {
            "set": bool(value),
            "required": True,
        }
    
    for var in optional_vars:
        value = os.getenv(var)
        status[var] = {
            "set": bool(value),
            "required": False,
        }
    
    return 200, {"env_status": status}

