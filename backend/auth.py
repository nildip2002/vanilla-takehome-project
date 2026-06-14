"""
Authentication Module — Token-based auth with Azure Key Vault.

Manages user authentication via email + access token pairs.
Tokens are stored in Azure Key Vault (cloud) or in-memory (local dev).

Allowed users:
  - nildip2002@outlook.com
  - betty.lau@bmo.com
  - ROXANA.SAREA@bmo.com
"""

import hashlib
import logging
import os
import secrets
from typing import Optional

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)

ALLOWED_EMAILS = [
    "nildip2002@outlook.com",
    "betty.lau@bmo.com",
    "roxana.sarea@bmo.com",
]

# In-memory token store for local dev (when Key Vault is not configured)
_local_tokens: dict[str, str] = {}


def _get_keyvault_client():
    """Get Azure Key Vault client if configured."""
    vault_url = os.environ.get("KEY_VAULT_URL")
    if not vault_url:
        return None
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient
        credential = DefaultAzureCredential()
        return SecretClient(vault_url=vault_url, credential=credential)
    except Exception as exc:
        logger.warning("Failed to connect to Key Vault: %s", exc)
        return None


def _secret_name_for_email(email: str) -> str:
    """Convert email to a valid Key Vault secret name (alphanumeric + hyphens)."""
    return "auth-token-" + hashlib.md5(email.lower().encode()).hexdigest()[:12]


def generate_token() -> str:
    """Generate a secure random access token."""
    return secrets.token_urlsafe(32)


def store_token(email: str, token: str) -> bool:
    """Store an access token for a user (Key Vault or local)."""
    email = email.lower().strip()
    if email not in ALLOWED_EMAILS:
        return False

    kv_client = _get_keyvault_client()
    if kv_client:
        try:
            secret_name = _secret_name_for_email(email)
            kv_client.set_secret(secret_name, token)
            logger.info("Stored token in Key Vault for %s", email)
            return True
        except Exception as exc:
            logger.error("Failed to store token in Key Vault: %s", exc)
            return False
    else:
        _local_tokens[email] = token
        logger.info("Stored token locally for %s (Key Vault not configured)", email)
        return True


def verify_token(email: str, token: str) -> bool:
    """Verify an access token against stored value."""
    email = email.lower().strip()
    if email not in ALLOWED_EMAILS:
        return False

    kv_client = _get_keyvault_client()
    if kv_client:
        try:
            secret_name = _secret_name_for_email(email)
            stored = kv_client.get_secret(secret_name)
            return secrets.compare_digest(stored.value, token)
        except Exception:
            return False
    else:
        stored = _local_tokens.get(email)
        if not stored:
            return False
        return secrets.compare_digest(stored, token)


def get_all_tokens() -> dict[str, str]:
    """Get all tokens (for initial setup/display). Only works locally."""
    return dict(_local_tokens)


def init_default_tokens() -> dict[str, str]:
    """Generate tokens for all allowed users if not already set."""
    generated = {}
    for email in ALLOWED_EMAILS:
        kv_client = _get_keyvault_client()
        if kv_client:
            try:
                secret_name = _secret_name_for_email(email)
                kv_client.get_secret(secret_name)
                continue
            except Exception:
                pass

        if email not in _local_tokens:
            token = generate_token()
            store_token(email, token)
            generated[email] = token

    return generated


def auth_required(request: Request) -> str:
    """FastAPI dependency that enforces authentication. Returns the email if valid."""
    if not os.environ.get("KEY_VAULT_URL") and not os.environ.get("AUTH_ENABLED"):
        return "local-dev@localhost"

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    parts = auth_header[7:].split(":", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=401, detail="Token format: email:token")

    email, token = parts[0], parts[1]
    if not verify_token(email, token):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return email
