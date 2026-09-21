"""
Cryptographic policy signing.

Turns policy YAML into a signable contract.

Design rationale:
- HMAC-SHA256 with a secret key stored outside the repo (env var).
- Signing is deterministic: same policy + same key -> same signature.
- Any byte change in the policy file changes the signature.
- The signature is recorded on every RoutingDecision and every TraceEvent.
- Audit can prove: "this decision used exactly this policy, unmodified."

Why HMAC and not PGP:
- HMAC is symmetric, simpler, and sufficient for internal governance.
- For public verification you would use Ed25519 or similar; that is out of scope.
"""

import hmac
import hashlib
import os
from pathlib import Path
from typing import Optional


DEFAULT_SECRET_ENV = "POLICY_SIGNING_KEY"


class PolicySigner:
    """
    Signs and verifies policy files using HMAC-SHA256.
    """

    def __init__(self, secret_key: Optional[bytes] = None):
        if secret_key is None:
            key_str = os.environ.get(DEFAULT_SECRET_ENV)
            if not key_str:
                # Development default. Never use in production.
                key_str = "dev-only-insecure-key-do-not-use"
            secret_key = key_str.encode()
        self.secret = secret_key

    def sign_file(self, path: Path | str) -> str:
        """Return the HMAC signature of a policy file's bytes."""
        data = Path(path).read_bytes()
        return hmac.new(self.secret, data, hashlib.sha256).hexdigest()

    def sign_bytes(self, data: bytes) -> str:
        return hmac.new(self.secret, data, hashlib.sha256).hexdigest()

    def verify_file(self, path: Path | str, expected_signature: str) -> bool:
        """Constant-time comparison of signature."""
        actual = self.sign_file(path)
        return hmac.compare_digest(actual, expected_signature)

    def verify_bytes(self, data: bytes, expected_signature: str) -> bool:
        actual = self.sign_bytes(data)
        return hmac.compare_digest(actual, expected_signature)


# Module-level default signer.
default_signer = PolicySigner()