"""JLCPCB Absolute Order Guard and Purchase Safety Barrier.

Strict Safety Invariants:
1. No automated purchasing, checkout, or monetary transaction may be initiated autonomously.
2. AI agents cannot bypass this guard.
3. Every order submission requires explicit interactive human Captain confirmation.
4. If approval token is missing, expired, or invalid, execution fails closed.
"""

from __future__ import annotations
import secrets
import time
from typing import Dict, Any, Optional


class OrderExecutionBlockedError(PermissionError):
    """Raised when an order placement attempt violates purchase safety policy."""
    pass


class OrderApprovalManager:
    """Manages ephemeral, time-bounded Captain approval tokens for order submissions."""

    TOKEN_LIFETIME_SECONDS = 300.0  # 5 minutes validity

    def __init__(self):
        self._pending_approvals: Dict[str, Dict[str, Any]] = {}

    def request_approval(self, order_summary: Dict[str, Any]) -> str:
        """Create a pending order approval request and return the token."""
        token = f"CAPTAIN-APPROVE-{secrets.token_hex(4).upper()}"
        self._pending_approvals[token] = {
            "summary": order_summary,
            "created_at": time.time(),
            "status": "PENDING",
        }
        return token

    def confirm_token(self, token: str) -> bool:
        """Human Captain confirms the approval token."""
        entry = self._pending_approvals.get(token)
        if not entry:
            return False
        if time.time() - entry["created_at"] > self.TOKEN_LIFETIME_SECONDS:
            del self._pending_approvals[token]
            return False
        entry["status"] = "CONFIRMED"
        return True

    def verify_and_consume(self, token: Optional[str]) -> bool:
        """Verify token is confirmed and unexpired, then consume it immediately."""
        if not token:
            raise OrderExecutionBlockedError(
                "ORDER REJECTED: Missing Captain approval token. "
                "Autonomous purchasing is strictly prohibited."
            )
        entry = self._pending_approvals.get(token)
        if not entry:
            raise OrderExecutionBlockedError(
                "ORDER REJECTED: Invalid or nonexistent approval token."
            )
        if time.time() - entry["created_at"] > self.TOKEN_LIFETIME_SECONDS:
            del self._pending_approvals[token]
            raise OrderExecutionBlockedError(
                "ORDER REJECTED: Captain approval token has expired."
            )
        if entry["status"] != "CONFIRMED":
            raise OrderExecutionBlockedError(
                f"ORDER REJECTED: Token '{token}' has not been confirmed by the Captain."
            )

        # Single-use consumption
        del self._pending_approvals[token]
        return True


_GLOBAL_ORDER_GUARD: Optional[OrderApprovalManager] = None


def get_order_guard() -> OrderApprovalManager:
    global _GLOBAL_ORDER_GUARD
    if _GLOBAL_ORDER_GUARD is None:
        _GLOBAL_ORDER_GUARD = OrderApprovalManager()
    return _GLOBAL_ORDER_GUARD
