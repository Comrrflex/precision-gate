import hashlib
import hmac
import json

import pytest


@pytest.fixture
def sign_api_output(monkeypatch):
    secret = "precision-test-only-key"
    monkeypatch.delenv("PRECISION_GATE_HMAC_SECRETS", raising=False)
    monkeypatch.setenv("PRECISION_GATE_HMAC_SECRET", secret)

    def sign(payload):
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        signature = hmac.new(secret.encode(), canonical.encode(), hashlib.sha256).hexdigest()
        return {**payload, "signature_hmac": signature}

    return sign
