"""Tests for strict config parsing (``Policy.from_dict`` / ``SandboxSpec.from_dict``).

A security policy must fail loud, never silently fall back to a default because
a key was misspelled — these pin that.
"""

import pytest

from gimle.hugin.sandbox.policy import Policy
from gimle.hugin.sandbox.sandbox import SandboxSpec


class TestPolicyFromDict:
    """Parsing the options.bash.policy block."""

    def test_empty_yields_conservative_defaults(self):
        """An absent/empty policy block is the default denylist policy."""
        assert Policy.from_dict(None) == Policy()
        assert Policy.from_dict({}) == Policy()

    def test_known_fields_are_applied(self):
        """Recognised keys are set, and list fields become tuples."""
        policy = Policy.from_dict(
            {"mode": "allowlist", "allow": ["ls", "cat"], "timeout_s": 30}
        )
        assert policy.mode == "allowlist"
        assert policy.allow == ("ls", "cat")
        assert policy.timeout_s == 30

    def test_unknown_key_raises(self):
        """A misspelled key is an error, not silently dropped."""
        with pytest.raises(ValueError, match="unknown policy keys"):
            Policy.from_dict({"modee": "allowlist"})

    def test_invalid_mode_raises(self):
        """An invalid mode literal is rejected."""
        with pytest.raises(ValueError, match="invalid policy mode"):
            Policy.from_dict({"mode": "allowlst"})

    def test_invalid_on_violation_raises(self):
        """An invalid on_violation literal is rejected."""
        with pytest.raises(ValueError, match="invalid on_violation"):
            Policy.from_dict({"on_violation": "maybe"})


class TestSandboxSpecFromDict:
    """Parsing the options.bash block into a SandboxSpec."""

    def test_backend_is_required(self):
        """A config must name its backend — there is no silent default."""
        with pytest.raises(ValueError, match="backend is required"):
            SandboxSpec.from_dict({"network": True})

    def test_policy_subblock_is_ignored(self):
        """The nested policy block belongs to Policy, not the spec."""
        spec = SandboxSpec.from_dict(
            {"backend": "local", "policy": {"mode": "allowlist"}}
        )
        assert spec.backend == "local"

    def test_unknown_key_raises(self):
        """An unknown spec key is an error."""
        with pytest.raises(ValueError, match="unknown sandbox keys"):
            SandboxSpec.from_dict({"backend": "local", "gpu": True})

    def test_invalid_backend_raises(self):
        """An unrecognised backend name is rejected."""
        with pytest.raises(ValueError, match="invalid backend"):
            SandboxSpec.from_dict({"backend": "vm"})

    def test_container_knobs_are_carried(self):
        """Resource knobs pass through for the container backends."""
        spec = SandboxSpec.from_dict(
            {"backend": "docker", "network": True, "memory": "4g"}
        )
        assert spec.network is True
        assert spec.memory == "4g"
