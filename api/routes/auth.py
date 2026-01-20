"""
Auth Routes
OAuth authentication and user session management

This module handles:
- Google OAuth flow (initiate and callback)
- JWT token management
- User session endpoints
- Logout and token revocation
"""

import os
import json
import time
import secrets
import urllib.parse
from typing import Tuple, Any, Optional, Dict

import jwt
import requests

# Try to import security modules
try:
    from ..security.auth import (
        create_jwt_token,
        verify_jwt_token,
        revoke_token,
        constant_time_compare,
    )
    from ..security.monitoring import log_auth_success, log_auth_failure
    _SECURITY_AVAILABLE = True
except ImportError:
    _SECURITY_AVAILABLE = False
    
    def verify_jwt_token(token: str) -> Optional[dict]:
        """Fallback JWT verification."""
        try:
            secret = os.getenv('JWT_SECRET', 'dev-secret')
            return jwt.decode(token, secret, algorithms=['HS256'])
        except Exception:
            return None
    
    def log_auth_success(*args, **kwargs):
        pass
    
    def log_auth_failure(*args, **kwargs):
        pass

from ..data.redis_client import get_redis


# ============== CONFIGURATION ==============

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# OAuth state TTL
OAUTH_STATE_TTL_SECONDS = 600  # 10 minutes

# JWT configuration
JWT_ALGORITHM = 'HS256'
JWT_EXPIRY_HOURS = 24 * 7  # 1 week


def _get_google_client_id() -> Optional[str]:
    """Get Google OAuth client ID."""
    return os.getenv('GOOGLE_CLIENT_ID')


def _get_google_client_secret() -> Optional[str]:
    """Get Google OAuth client secret."""
    return os.getenv('GOOGLE_CLIENT_SECRET')


def _get_jwt_secret() -> str:
    """Get JWT signing secret."""
    secret = os.getenv('JWT_SECRET')
    if not secret:
        if os.getenv('VERCEL_ENV', 'development') == 'development':
            return "INSECURE_DEV_SECRET_DO_NOT_USE_IN_PRODUCTION"
        raise RuntimeError("JWT_SECRET environment variable is required in production")
    return secret


def _get_allowed_origins() -> list:
    """Get allowed CORS origins."""
    origins = os.getenv('ALLOWED_ORIGINS', 'https://embeddle.vercel.app').split(',')
    return [o.strip() for o in origins if o.strip()]


# ============== OAUTH HELPERS ==============

def generate_oauth_state(redirect_uri: str, return_to: str) -> Optional[str]:
    """
    Generate and store OAuth state token.
    
    Args:
        redirect_uri: OAuth callback URI
        return_to: Frontend URL to return to after auth
        
    Returns:
        State token string, or None if storage failed
    """
    redis = get_redis()
    if not redis:
        return None
    
    try:
        state = secrets.token_urlsafe(24)
        redis.setex(
            f"oauth_state:{state}",
            OAUTH_STATE_TTL_SECONDS,
            json.dumps({
                "redirect_uri": redirect_uri,
                "return_to": return_to,
                "created_at": int(time.time()),
            }),
        )
        return state
    except Exception as e:
        print(f"[AUTH] OAuth state store failed: {e}")
        return None


def validate_oauth_state(state: str) -> Tuple[bool, Optional[Dict[str, str]]]:
    """
    Validate and consume OAuth state token (single-use).
    
    Args:
        state: State token from callback
        
    Returns:
        Tuple of (is_valid, state_data)
    """
    if not state:
        return False, None
    
    redis = get_redis()
    if not redis:
        return False, None
    
    try:
        raw = redis.get(f"oauth_state:{state}")
        if not raw:
            return False, None
        
        data = json.loads(raw)
        
        # Delete immediately (single-use)
        redis.delete(f"oauth_state:{state}")
        
        return True, data
    except Exception as e:
        print(f"[AUTH] OAuth state validation failed: {e}")
        return False, None


def exchange_code_for_tokens(code: str, redirect_uri: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Exchange OAuth authorization code for tokens.
    
    Args:
        code: Authorization code from Google
        redirect_uri: Redirect URI used in auth request
        
    Returns:
        Tuple of (success, token_data or error_data)
    """
    client_id = _get_google_client_id()
    client_secret = _get_google_client_secret()
    
    if not client_id or not client_secret:
        return False, {"error": "oauth_not_configured"}
    
    try:
        response = requests.post(GOOGLE_TOKEN_URL, data={
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri,
        }, timeout=10)
        
        if not response.ok:
            error_data = {}
            try:
                error_data = response.json()
            except Exception:
                pass
            return False, {
                "error": error_data.get("error", "token_exchange_failed"),
                "error_description": error_data.get("error_description", ""),
            }
        
        return True, response.json()
    except requests.Timeout:
        return False, {"error": "timeout"}
    except Exception as e:
        return False, {"error": str(e)}


def fetch_google_user_info(access_token: str) -> Tuple[bool, Dict[str, Any]]:
    """
    Fetch user info from Google using access token.
    
    Args:
        access_token: OAuth access token
        
    Returns:
        Tuple of (success, user_info or error_data)
    """
    try:
        response = requests.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        
        if not response.ok:
            return False, {"error": "userinfo_fetch_failed"}
        
        return True, response.json()
    except Exception as e:
        return False, {"error": str(e)}


# ============== JWT HELPERS ==============

def create_user_jwt(user_data: Dict[str, Any]) -> str:
    """
    Create JWT token for authenticated user.
    
    Args:
        user_data: Dict with 'id', 'email', 'name', 'avatar' keys
        
    Returns:
        Encoded JWT token string
    """
    if _SECURITY_AVAILABLE:
        return create_jwt_token(user_data)
    
    # Fallback implementation
    now = int(time.time())
    payload = {
        'sub': user_data['id'],
        'email': user_data.get('email', ''),
        'name': user_data.get('name', ''),
        'avatar': user_data.get('avatar', ''),
        'iat': now,
        'exp': now + (JWT_EXPIRY_HOURS * 3600),
        'jti': secrets.token_hex(16),
    }
    return jwt.encode(payload, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_user_jwt(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode JWT token.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload dict, or None if invalid
    """
    return verify_jwt_token(token)


# ============== ROUTE HANDLERS ==============

def handle_auth_routes(
    handler,
    method: str,
    path: str,
    query: Dict[str, str],
    body: Dict[str, Any],
    headers: Dict[str, str],
    client_ip: str,
) -> Optional[Tuple[int, Any]]:
    """
    Route handler for authentication endpoints.
    
    Args:
        handler: HTTP request handler instance
        method: HTTP method (GET, POST)
        path: Request path
        query: Query parameters
        body: Request body (for POST)
        headers: Request headers
        client_ip: Client IP address
        
    Returns:
        Tuple of (status_code, response_body) or None if not handled
    """
    
    # GET /api/auth/google - Redirect to Google OAuth
    if path == '/api/auth/google' and method == 'GET':
        client_id = _get_google_client_id()
        client_secret = _get_google_client_secret()
        
        if not client_id or not client_secret:
            return 500, {"detail": "OAuth not configured"}
        
        # Compute redirect URI
        request_base = _get_request_base_url(headers)
        redirect_uri = os.getenv('OAUTH_REDIRECT_URI') or f"{request_base}/api/auth/callback"
        
        # Generate state token
        state = generate_oauth_state(redirect_uri, request_base)
        
        params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'consent',
        }
        if state:
            params['state'] = state
        
        auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        
        # Return redirect response
        return "redirect", auth_url
    
    # GET /api/auth/callback - Handle OAuth callback
    if path == '/api/auth/callback' and method == 'GET':
        return _handle_oauth_callback(query, headers, client_ip)
    
    # GET /api/auth/me - Get current user info
    if path == '/api/auth/me' and method == 'GET':
        return _handle_get_current_user(headers)
    
    # POST /api/auth/logout - Logout user
    if path == '/api/auth/logout' and method == 'POST':
        return _handle_logout(headers, body)
    
    return None  # Not handled


def _get_request_base_url(headers: Dict[str, str]) -> str:
    """Extract base URL from request headers."""
    # Try X-Forwarded headers first (for proxied requests)
    proto = headers.get('X-Forwarded-Proto', 'https')
    host = headers.get('X-Forwarded-Host') or headers.get('Host', '')
    
    if host:
        return f"{proto}://{host}"
    
    # Fallback to default
    return os.getenv('SITE_URL', 'https://embeddle.vercel.app')


def _handle_oauth_callback(
    query: Dict[str, str],
    headers: Dict[str, str],
    client_ip: str
) -> Tuple[Any, Any]:
    """Handle OAuth callback from Google."""
    from ..data.user_repository import get_user_by_email, save_user
    
    code = query.get('code', '')
    error = query.get('error', '')
    state = query.get('state', '')
    
    # Validate state
    is_valid, state_data = validate_oauth_state(state)
    redirect_uri = state_data.get('redirect_uri', '') if state_data else ''
    return_to = state_data.get('return_to', '') if state_data else ''
    
    # Build redirect helper
    def redirect_with_params(params: Dict[str, str]) -> Tuple[str, str]:
        qs = urllib.parse.urlencode({k: v for k, v in params.items() if v})
        
        # Validate return_to
        if return_to:
            allowed_origins = _get_allowed_origins()
            is_allowed = any(return_to.startswith(o) for o in allowed_origins)
            if os.getenv('VERCEL_ENV', 'development') == 'development':
                is_allowed = is_allowed or return_to.startswith('http://localhost:')
            
            if is_allowed:
                target = return_to.rstrip('/') + '/?' + qs
                return "redirect", target
        
        return "redirect", '/?' + qs
    
    # Check for errors
    if not is_valid:
        log_auth_failure(client_ip, "invalid_state")
        return redirect_with_params({'auth_error': 'invalid_state'})
    
    if error:
        log_auth_failure(client_ip, error)
        return redirect_with_params({
            'auth_error': error,
            'auth_error_description': query.get('error_description', ''),
        })
    
    if not code:
        log_auth_failure(client_ip, "no_code")
        return redirect_with_params({'auth_error': 'no_code'})
    
    # Exchange code for tokens
    success, token_data = exchange_code_for_tokens(code, redirect_uri)
    if not success:
        log_auth_failure(client_ip, token_data.get('error', 'token_exchange_failed'))
        return redirect_with_params({
            'auth_error': 'token_exchange_failed',
            'google_error': token_data.get('error', ''),
            'google_error_description': token_data.get('error_description', ''),
        })
    
    access_token = token_data.get('access_token')
    if not access_token:
        log_auth_failure(client_ip, "no_access_token")
        return redirect_with_params({'auth_error': 'no_access_token'})
    
    # Fetch user info
    success, user_info = fetch_google_user_info(access_token)
    if not success:
        log_auth_failure(client_ip, "userinfo_failed")
        return redirect_with_params({'auth_error': 'userinfo_failed'})
    
    # Create or update user
    email = user_info.get('email', '').lower()
    google_id = user_info.get('id', '')
    name = user_info.get('name', email.split('@')[0])
    avatar = user_info.get('picture', '')
    
    if not email:
        log_auth_failure(client_ip, "no_email")
        return redirect_with_params({'auth_error': 'no_email'})
    
    # Look up existing user
    user = get_user_by_email(email)
    
    if not user:
        # Create new user
        user = {
            'id': google_id,
            'email': email,
            'name': name,
            'avatar': avatar,
            'created_at': int(time.time()),
            'stats': {},
            'cosmetics': {},
            'owned_cosmetics': {},
            'wallet': {'credits': 0},
        }
    else:
        # Update existing user
        user['name'] = name
        user['avatar'] = avatar
        user['last_login'] = int(time.time())
    
    save_user(user)
    
    # Create JWT
    jwt_token = create_user_jwt({
        'id': user['id'],
        'email': email,
        'name': name,
        'avatar': avatar,
    })
    
    log_auth_success(client_ip, user['id'], 'google')
    
    return redirect_with_params({'auth_token': jwt_token})


def _handle_get_current_user(headers: Dict[str, str]) -> Tuple[int, Any]:
    """Handle GET /api/auth/me - get current user info."""
    from ..data.user_repository import get_user_by_id
    
    auth_header = headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return 401, {"detail": "Not authenticated"}
    
    token = auth_header[7:]
    payload = verify_user_jwt(token)
    
    if not payload:
        return 401, {"detail": "Invalid token"}
    
    user_id = payload.get('sub')
    if not user_id:
        return 401, {"detail": "Invalid token"}
    
    # Get full user data
    user = get_user_by_id(user_id)
    
    if not user:
        # User exists in JWT but not in database - return basic info
        return 200, {
            'id': user_id,
            'email': payload.get('email', ''),
            'name': payload.get('name', ''),
            'avatar': payload.get('avatar', ''),
            'is_admin': False,
        }
    
    # Check admin status
    admin_emails = os.getenv('ADMIN_EMAILS', '').split(',')
    admin_emails = [e.strip().lower() for e in admin_emails if e.strip()]
    is_admin = user.get('email', '').lower() in admin_emails
    
    return 200, {
        'id': user['id'],
        'email': user.get('email', ''),
        'name': user.get('name', ''),
        'avatar': user.get('avatar', ''),
        'is_admin': is_admin,
        'is_donor': user.get('is_donor', False),
        'stats': user.get('stats', {}),
    }


def _handle_logout(headers: Dict[str, str], body: Dict[str, Any]) -> Tuple[int, Any]:
    """Handle POST /api/auth/logout - logout user."""
    auth_header = headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return 200, {"ok": True}  # Already logged out
    
    token = auth_header[7:]
    payload = verify_user_jwt(token)
    
    if payload and _SECURITY_AVAILABLE:
        # Revoke the token
        jti = payload.get('jti')
        if jti:
            exp = payload.get('exp', 0)
            ttl = max(0, exp - int(time.time()))
            revoke_token(jti, ttl)
    
    return 200, {"ok": True}

