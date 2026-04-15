import hashlib
import hmac
import secrets


def generate_api_key(prefix: str = "brand") -> str:
    return f"{prefix}_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def verify_api_key(raw_key: str, stored_hash: str) -> bool:
    computed = hash_api_key(raw_key)
    return hmac.compare_digest(computed, stored_hash)
