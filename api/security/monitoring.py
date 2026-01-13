"""
Security Monitoring Module

Provides:
- Security event logging
- Rate limit breach alerts
- Unusual API pattern detection
- Audit trail for sensitive operations
"""

import os
import time
import json
import hashlib
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict


class SecurityEventType(Enum):
    """Types of security events to monitor."""
    
    # Authentication events
    AUTH_SUCCESS = "auth_success"
    AUTH_FAILURE = "auth_failure"
    AUTH_ADMIN_LOGIN = "auth_admin_login"
    TOKEN_REFRESH = "token_refresh"
    TOKEN_REVOKED = "token_revoked"
    
    # Rate limiting events
    RATE_LIMIT_HIT = "rate_limit_hit"
    RATE_LIMIT_BLOCKED = "rate_limit_blocked"
    
    # Suspicious activity
    SUSPICIOUS_INPUT = "suspicious_input"
    INVALID_TOKEN = "invalid_token"
    UNAUTHORIZED_ACCESS = "unauthorized_access"
    
    # Webhook events
    WEBHOOK_RECEIVED = "webhook_received"
    WEBHOOK_INVALID = "webhook_invalid"
    WEBHOOK_SUCCESS = "webhook_success"
    
    # Admin actions
    ADMIN_ACTION = "admin_action"
    
    # Game events (for audit)
    GAME_CREATED = "game_created"
    GAME_JOINED = "game_joined"
    
    # Cost-related
    EMBEDDING_QUOTA_WARNING = "embedding_quota_warning"
    EMBEDDING_QUOTA_EXCEEDED = "embedding_quota_exceeded"


@dataclass
class SecurityEvent:
    """A security event to be logged."""
    event_type: SecurityEventType
    timestamp: int
    ip_address: Optional[str]
    user_id: Optional[str]
    details: Dict[str, Any]
    severity: str  # "info", "warning", "error", "critical"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "ip_address": self.ip_address,
            "user_id": self.user_id,
            "details": self.details,
            "severity": self.severity,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class SecurityMonitor:
    """
    Centralized security monitoring and alerting.
    
    Tracks security events and can trigger alerts based on patterns.
    """
    
    # Thresholds for alerting
    RATE_LIMIT_ALERT_THRESHOLD = 10  # Alert after N rate limits from same IP
    AUTH_FAILURE_ALERT_THRESHOLD = 5  # Alert after N auth failures from same IP
    SUSPICIOUS_PATTERN_WINDOW = 300  # 5 minute window for pattern detection
    
    def __init__(self):
        self._redis_client = None
        self._local_cache: Dict[str, List[SecurityEvent]] = defaultdict(list)
    
    def _get_redis(self):
        """Get Redis client (lazy initialization)."""
        if self._redis_client is None:
            try:
                from upstash_redis import Redis
                self._redis_client = Redis(
                    url=os.getenv("UPSTASH_REDIS_REST_URL"),
                    token=os.getenv("UPSTASH_REDIS_REST_TOKEN"),
                )
            except Exception as e:
                print(f"[SECURITY] Failed to initialize Redis for monitoring: {e}")
                return None
        return self._redis_client
    
    def log_event(self, event: SecurityEvent):
        """
        Log a security event.
        
        Events are logged to:
        1. Console (always)
        2. Redis (if available, for persistence and alerting)
        """
        # Console logging
        log_level = {
            "info": "INFO",
            "warning": "WARN",
            "error": "ERROR",
            "critical": "CRIT",
        }.get(event.severity, "INFO")
        
        print(f"[SECURITY {log_level}] {event.event_type.value}: {json.dumps(event.details)}")
        
        # Redis logging for persistence
        redis = self._get_redis()
        if redis:
            try:
                # Store in sorted set by timestamp for efficient querying
                key = f"security_events:{event.event_type.value}"
                redis.zadd(key, {event.to_json(): event.timestamp})
                
                # Trim to last 1000 events per type
                redis.zremrangebyrank(key, 0, -1001)
                
                # Set expiry (7 days)
                redis.expire(key, 604800)
                
                # Check for alert conditions
                self._check_alert_conditions(event)
                
            except Exception as e:
                print(f"[SECURITY] Failed to persist event: {e}")
    
    def _check_alert_conditions(self, event: SecurityEvent):
        """Check if event triggers any alert conditions."""
        redis = self._get_redis()
        if not redis:
            return
        
        try:
            now = int(time.time())
            window_start = now - self.SUSPICIOUS_PATTERN_WINDOW
            
            # Check rate limit patterns
            if event.event_type == SecurityEventType.RATE_LIMIT_HIT:
                ip = event.ip_address
                if ip:
                    key = f"security_alerts:ratelimit:{ip}"
                    count = redis.incr(key)
                    redis.expire(key, self.SUSPICIOUS_PATTERN_WINDOW)
                    
                    if count and int(count) >= self.RATE_LIMIT_ALERT_THRESHOLD:
                        self._trigger_alert(
                            f"Rate limit abuse detected from IP {ip}",
                            {"ip": ip, "count": int(count)},
                        )
            
            # Check auth failure patterns
            elif event.event_type == SecurityEventType.AUTH_FAILURE:
                ip = event.ip_address
                if ip:
                    key = f"security_alerts:authfail:{ip}"
                    count = redis.incr(key)
                    redis.expire(key, self.SUSPICIOUS_PATTERN_WINDOW)
                    
                    if count and int(count) >= self.AUTH_FAILURE_ALERT_THRESHOLD:
                        self._trigger_alert(
                            f"Possible brute force attack from IP {ip}",
                            {"ip": ip, "count": int(count)},
                        )
            
            # Check webhook abuse
            elif event.event_type == SecurityEventType.WEBHOOK_INVALID:
                ip = event.ip_address
                if ip:
                    key = f"security_alerts:webhook:{ip}"
                    count = redis.incr(key)
                    redis.expire(key, self.SUSPICIOUS_PATTERN_WINDOW)
                    
                    if count and int(count) >= 3:
                        self._trigger_alert(
                            f"Invalid webhook attempts from IP {ip}",
                            {"ip": ip, "count": int(count)},
                        )
                        
        except Exception as e:
            print(f"[SECURITY] Alert check failed: {e}")
    
    def _trigger_alert(self, message: str, details: Dict[str, Any]):
        """
        Trigger a security alert.
        
        In production, this could send to:
        - Email
        - Slack
        - PagerDuty
        - etc.
        
        For now, we log to console and Redis.
        """
        alert = {
            "message": message,
            "details": details,
            "timestamp": int(time.time()),
        }
        
        print(f"[SECURITY ALERT] {message}: {json.dumps(details)}")
        
        redis = self._get_redis()
        if redis:
            try:
                redis.lpush("security_alerts", json.dumps(alert))
                redis.ltrim("security_alerts", 0, 99)  # Keep last 100 alerts
            except Exception:
                pass
    
    def get_recent_events(
        self,
        event_type: Optional[SecurityEventType] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get recent security events (for admin dashboard)."""
        redis = self._get_redis()
        if not redis:
            return []
        
        try:
            if event_type:
                key = f"security_events:{event_type.value}"
                events = redis.zrevrange(key, 0, limit - 1)
            else:
                # Get from all event types
                events = []
                for et in SecurityEventType:
                    key = f"security_events:{et.value}"
                    type_events = redis.zrevrange(key, 0, 20) or []
                    events.extend(type_events)
            
            # Parse and sort
            parsed = []
            for e in events:
                try:
                    parsed.append(json.loads(e))
                except Exception:
                    pass
            
            parsed.sort(key=lambda x: x.get("timestamp", 0), reverse=True)
            return parsed[:limit]
            
        except Exception as e:
            print(f"[SECURITY] Failed to get events: {e}")
            return []
    
    def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent security alerts (for admin dashboard)."""
        redis = self._get_redis()
        if not redis:
            return []
        
        try:
            alerts = redis.lrange("security_alerts", 0, limit - 1) or []
            return [json.loads(a) for a in alerts if a]
        except Exception:
            return []


# Global monitor instance
_monitor: Optional[SecurityMonitor] = None


def get_security_monitor() -> SecurityMonitor:
    """Get the global security monitor instance."""
    global _monitor
    if _monitor is None:
        _monitor = SecurityMonitor()
    return _monitor


def log_security_event(
    event_type: SecurityEventType,
    ip_address: Optional[str] = None,
    user_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    severity: str = "info",
):
    """
    Convenience function to log a security event.
    
    Args:
        event_type: Type of security event
        ip_address: Client IP address
        user_id: User ID if authenticated
        details: Additional event details
        severity: "info", "warning", "error", or "critical"
    """
    event = SecurityEvent(
        event_type=event_type,
        timestamp=int(time.time()),
        ip_address=ip_address,
        user_id=user_id,
        details=details or {},
        severity=severity,
    )
    
    get_security_monitor().log_event(event)


# Convenience functions for common events

def log_auth_success(ip: str, user_id: str, method: str = "google"):
    """Log successful authentication."""
    log_security_event(
        SecurityEventType.AUTH_SUCCESS,
        ip_address=ip,
        user_id=user_id,
        details={"method": method},
        severity="info",
    )


def log_auth_failure(ip: str, reason: str, user_id: Optional[str] = None):
    """Log failed authentication attempt."""
    log_security_event(
        SecurityEventType.AUTH_FAILURE,
        ip_address=ip,
        user_id=user_id,
        details={"reason": reason},
        severity="warning",
    )


def log_rate_limit_hit(ip: str, endpoint: str, user_id: Optional[str] = None):
    """Log rate limit being hit."""
    log_security_event(
        SecurityEventType.RATE_LIMIT_HIT,
        ip_address=ip,
        user_id=user_id,
        details={"endpoint": endpoint},
        severity="warning",
    )


def log_rate_limit_blocked(ip: str, endpoint: str, duration: int, user_id: Optional[str] = None):
    """Log IP being blocked for repeated rate limit violations."""
    log_security_event(
        SecurityEventType.RATE_LIMIT_BLOCKED,
        ip_address=ip,
        user_id=user_id,
        details={"endpoint": endpoint, "block_duration": duration},
        severity="error",
    )


def log_webhook_event(ip: str, webhook_type: str, success: bool, details: Optional[Dict] = None):
    """Log webhook event."""
    event_type = SecurityEventType.WEBHOOK_SUCCESS if success else SecurityEventType.WEBHOOK_INVALID
    log_security_event(
        event_type,
        ip_address=ip,
        details={"webhook_type": webhook_type, **(details or {})},
        severity="info" if success else "warning",
    )


def log_admin_action(ip: str, user_id: str, action: str, details: Optional[Dict] = None):
    """Log admin action for audit trail."""
    log_security_event(
        SecurityEventType.ADMIN_ACTION,
        ip_address=ip,
        user_id=user_id,
        details={"action": action, **(details or {})},
        severity="info",
    )


def log_suspicious_input(ip: str, input_type: str, value_preview: str, user_id: Optional[str] = None):
    """Log suspicious input that failed validation."""
    # Truncate value preview for safety
    preview = value_preview[:50] + "..." if len(value_preview) > 50 else value_preview
    log_security_event(
        SecurityEventType.SUSPICIOUS_INPUT,
        ip_address=ip,
        user_id=user_id,
        details={"input_type": input_type, "preview": preview},
        severity="warning",
    )

