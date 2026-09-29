"""Bounded canonical records for the local transport experiment."""

import base64
import binascii
import json
from typing import Any

import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

MAX_RECORD_BYTES = 65536
DOMAIN = b"HUGIN-SWARM-EXPERIMENT-v0\x00"


class ProtocolError(ValueError):
    """Report a constant diagnostic without reflecting untrusted material."""

    def __init__(self) -> None:
        """Keep all wire-validation errors safe for diagnostics."""
        super().__init__("invalid_record")


def _validate(value: Any, depth: int = 0) -> None:
    if depth > 8:
        raise ProtocolError()
    if value is None or type(value) in (str, bool):
        return
    if type(value) is int and abs(value) <= 9007199254740991:
        return
    if type(value) is list:
        for item in value:
            _validate(item, depth + 1)
        return
    if type(value) is dict and all(type(k) is str for k in value):
        for item in value.values():
            _validate(item, depth + 1)
        return
    raise ProtocolError()


def encode(value: dict[str, Any]) -> bytes:
    """Encode a size/depth-limited canonical object, never arbitrary objects."""
    try:
        _validate(value)
        result = rfc8785.dumps(value)
        if len(result) > MAX_RECORD_BYTES:
            raise ProtocolError()
        return result
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProtocolError() from None


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ProtocolError()
        result[key] = value
    return result


def decode(raw: bytes) -> dict[str, Any]:
    """Reject duplicate keys, floats, deep nesting and noncanonical records."""
    if len(raw) > MAX_RECORD_BYTES:
        raise ProtocolError()
    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique)
        if not isinstance(value, dict) or encode(value) != raw:
            raise ProtocolError()
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ProtocolError() from None


def sign(payload: dict[str, Any], key: Ed25519PrivateKey) -> dict[str, Any]:
    """Sign semantic fields with a protocol-specific domain separator."""
    immutable_payload = decode(encode(payload))
    signature = key.sign(DOMAIN + encode(immutable_payload))
    return {
        "payload": immutable_payload,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def verify(record: Any, key: Ed25519PublicKey) -> dict[str, Any]:
    """Verify an exact signed wrapper and return an independent payload."""
    try:
        if type(record) is not dict or set(record) != {"payload", "signature"}:
            raise ProtocolError()
        if type(record["signature"]) is not str:
            raise ProtocolError()
        signature = base64.b64decode(record["signature"], validate=True)
        if (
            len(signature) != 64
            or base64.b64encode(signature).decode("ascii")
            != record["signature"]
        ):
            raise ProtocolError()
        raw = encode(record["payload"])
        key.verify(signature, DOMAIN + raw)
        return decode(raw)
    except (InvalidSignature, ValueError, TypeError, binascii.Error):
        raise ProtocolError() from None


def fields(record: Any, names: set[str]) -> None:
    """Reject missing and unknown fields in a versioned object."""
    if type(record) is not dict or set(record) != names:
        raise ProtocolError()


def integer(value: Any, minimum: int = 0) -> int:
    """Require a bounded integer instead of accepting bool as an integer."""
    if type(value) is not int or not minimum <= value <= 9007199254740991:
        raise ProtocolError()
    return int(value)
