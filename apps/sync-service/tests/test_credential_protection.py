import base64
import sys

import pytest

from app.credential_protection import (
    CredentialProtectionError,
    DpapiCredentialProtector,
)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows DPAPI only")
def test_dpapi_round_trip_is_not_plaintext():
    protector = DpapiCredentialProtector()

    encrypted = protector.protect("secret-value")

    assert encrypted != "secret-value"
    assert b"secret-value" not in base64.b64decode(encrypted)
    assert protector.unprotect(encrypted) == "secret-value"


def test_unprotect_rejects_invalid_base64():
    with pytest.raises(
        CredentialProtectionError, match="stored credential cannot be decrypted"
    ):
        DpapiCredentialProtector().unprotect("not-base64!!")
