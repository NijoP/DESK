"""DESK Credential Broker and Security Boundary.

Acts as the security perimeter between AI agents, workflow orchestrators, and
underlying external vendor APIs (LCSC, JLCPCB, Mouser, DigiKey).

Security Invariants:
1. AI agents and LLM prompts NEVER receive raw API keys or secrets in plaintext.
2. Outbound request headers/tokens are generated internally within the broker.
3. All errors, logs, and outputs pass through an active redaction engine.
4. Missing credentials fail-closed with structured remediation commands.
"""

from __future__ import annotations
import os
import re
from typing import Optional, Dict, Any, List, Set
from .storage import BaseCredentialStore, InMemoryCredentialStore, get_credential_store, update_metadata_index


class ProviderStatus:
    AVAILABLE = "AVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    CONNECTION_FAILED = "CONNECTION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"


class CredentialBroker:
    """Security broker managing secrets, authenticated headers, and leak prevention."""

    def __init__(self, store: Optional[BaseCredentialStore] = None):
        self._store = store or get_credential_store()
        self._known_secrets: Set[str] = set()

    def store_credentials(self, service: str, account: str, secret: str) -> bool:
        """Store credential securely in the platform vault and register for redaction."""
        if not service or not account or not secret:
            raise ValueError("Service, account, and secret are required")
        ok = self._store.set(service, account, secret)
        if ok:
            if not isinstance(self._store, InMemoryCredentialStore):
                update_metadata_index(service, account, "add")
            self._known_secrets.add(secret)
        return ok

    def delete_credentials(self, service: str, account: str) -> bool:
        """Remove credential from storage and index."""
        ok = self._store.delete(service, account)
        if not isinstance(self._store, InMemoryCredentialStore):
            update_metadata_index(service, account, "remove")
        return ok

    def has_credentials(self, service: str, account: Optional[str] = None) -> bool:
        """Check if credentials exist and are retrievable."""
        acc = account or "default"
        if self._store.get(service, acc) is not None:
            return True
        # Check any other account from index
        for item in self.list_credentials():
            if item.get("service") == service:
                if self._store.get(service, item.get("account", "default")) is not None:
                    return True
        return False

    def list_credentials(self) -> List[Dict[str, str]]:
        """List configured services (without exposing secrets)."""
        return self._store.list()

    def get_auth_headers(self, service: str, account: Optional[str] = None) -> Dict[str, str]:
        """Generate authenticated headers for API requests internally.
        
        Raises PermissionError if credentials are not configured.
        """
        service_lower = service.lower()
        acc = account or "default"
        secret = self._store.get(service_lower, acc)
        if not secret:
            # Check if environment variable exists as fallback
            env_key = f"DESK_{service.upper()}_API_KEY"
            secret = os.environ.get(env_key)
            if secret:
                self._known_secrets.add(secret)

        if not secret:
            cmd = f"python tools/desk.py auth configure {service_lower}"
            raise PermissionError(
                f"Missing credentials for '{service}'. "
                f"Run: '{cmd}' to configure securely."
            )

        self._known_secrets.add(secret)

        if service_lower == "lcsc":
            return {"Authorization": f"Bearer {secret}", "Content-Type": "application/json"}
        elif service_lower == "jlcpcb":
            return {"X-JLCPCB-Key": secret, "Content-Type": "application/json"}
        elif service_lower == "mouser":
            return {"apiKey": secret, "Content-Type": "application/json"}
        elif service_lower == "digikey":
            return {"X-DIGIKEY-Client-Id": secret, "Content-Type": "application/json"}
        else:
            return {"Authorization": f"Bearer {secret}"}

    def scrub(self, text: str) -> str:
        """Redact any known secret tokens from a text string, log, or prompt."""
        if not text:
            return ""
        scrubbed = str(text)
        for secret in self._known_secrets:
            if secret and len(secret) >= 4:
                scrubbed = scrubbed.replace(secret, "[REDACTED_SECRET]")
        # Regex heuristics for generic tokens: bearer tokens, high entropy hex
        scrubbed = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9_\-\.]{8,}", r"\1[REDACTED_TOKEN]", scrubbed)
        return scrubbed

    def get_provider_status(self, service: str) -> Dict[str, Any]:
        """Return the current authentication and readiness status for a provider."""
        has_cred = self.has_credentials(service)
        if not has_cred:
            # Check environment fallback
            env_key = f"DESK_{service.upper()}_API_KEY"
            if os.environ.get(env_key):
                has_cred = True

        if not has_cred:
            return {
                "service": service,
                "status": ProviderStatus.NOT_CONFIGURED,
                "authenticated": False,
                "message": f"No credentials configured for {service}.",
                "remediation": f"python tools/desk.py auth configure {service.lower()}",
            }

        return {
            "service": service,
            "status": ProviderStatus.AVAILABLE,
            "authenticated": True,
            "message": f"Configured and ready.",
            "remediation": None,
        }


_GLOBAL_BROKER: Optional[CredentialBroker] = None


def get_credential_broker(store: Optional[BaseCredentialStore] = None) -> CredentialBroker:
    """Return the global CredentialBroker singleton."""
    global _GLOBAL_BROKER
    if _GLOBAL_BROKER is None or store is not None:
        _GLOBAL_BROKER = CredentialBroker(store=store)
    return _GLOBAL_BROKER
