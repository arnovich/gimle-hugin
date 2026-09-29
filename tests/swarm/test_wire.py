"""Bound parsing before cryptographic verification or error reporting."""

import pytest

from gimle.hugin.swarm.wire import ProtocolError, decode, encode, sign, verify


@pytest.mark.parametrize(
    "raw",
    [
        b'{"v":0,"v":1}',
        b'{"value":NaN}',
        b'{"value":1.5}',
        b'{"value":9007199254740992}',
        b"[]",
        b"\xff",
        b'{"value":' + b"[" * 10 + b"0" + b"]" * 10 + b"}",
        b'{"value":"' + b"x" * 65536 + b'"}',
    ],
)
def test_invalid_wire_data_is_bounded_and_redacted(raw):
    """Reject ambiguous/oversized input with a constant safe error."""
    with pytest.raises(ProtocolError) as error:
        decode(raw)
    assert str(error.value) == "invalid_record"


def test_signature_is_canonical_and_detects_tampering(swarm_material):
    """Canonical key ordering verifies; changed semantic content does not."""
    key = swarm_material.alice.key
    signed = sign({"v": 0, "kind": "probe", "a": 1}, key)
    assert verify(signed, key.public_key()) == signed["payload"]
    assert decode(encode(signed)) == signed
    signed["payload"]["a"] = 2
    with pytest.raises(ProtocolError):
        verify(signed, key.public_key())
