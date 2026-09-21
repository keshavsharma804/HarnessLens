"""Verify policy signing detects tampering and is deterministic."""

import tempfile
from pathlib import Path

from app.policy_signer import PolicySigner


def test_signature_is_deterministic():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.yaml"
        p.write_text("version: 1\n")
        signer = PolicySigner(secret_key=b"test-key")
        sig1 = signer.sign_file(p)
        sig2 = signer.sign_file(p)
        assert sig1 == sig2


def test_signature_changes_on_content_change():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.yaml"
        signer = PolicySigner(secret_key=b"test-key")

        p.write_text("version: 1\n")
        sig1 = signer.sign_file(p)

        p.write_text("version: 2\n")
        sig2 = signer.sign_file(p)

        assert sig1 != sig2


def test_verify_accepts_correct_signature():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.yaml"
        p.write_text("version: 1\n")
        signer = PolicySigner(secret_key=b"test-key")
        sig = signer.sign_file(p)
        assert signer.verify_file(p, sig) is True


def test_verify_rejects_tampered_signature():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.yaml"
        p.write_text("version: 1\n")
        signer = PolicySigner(secret_key=b"test-key")
        assert signer.verify_file(p, "deadbeef") is False


def test_different_keys_produce_different_signatures():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "policy.yaml"
        p.write_text("version: 1\n")
        s1 = PolicySigner(secret_key=b"key-a").sign_file(p)
        s2 = PolicySigner(secret_key=b"key-b").sign_file(p)
        assert s1 != s2