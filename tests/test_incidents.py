import io
import itertools
import pytest
from relayvault import incidents, settings, os_actions
from relayvault.terminal import Terminal
from relayvault.auth import RetryPolicy, BackoffError


@pytest.mark.parametrize(
    "enabled,bound,allowed,armed,maintenance",
    list(itertools.product([False, True], repeat=5)),
)
def test_every_gate_required(monkeypatch, enabled, bound, allowed, armed, maintenance):
    calls = []
    monkeypatch.setattr(
        os_actions, "perform_os_action", lambda action: calls.append(action)
    )
    policy = {
        "enabled": enabled,
        "allowed_actions": ["shutdown"] if allowed else [],
        "bindings": {"channel_reset": "shutdown"} if bound else {},
    }
    incidents.channel_reset(
        Terminal(io.StringIO(), effects=False),
        policy,
        armed=armed,
        maintenance=maintenance,
    )
    assert calls == (
        ["shutdown"]
        if enabled and bound and allowed and armed and not maintenance
        else []
    )


def test_local_backoff_persists_independently_of_effects(tmp_path, monkeypatch):
    monkeypatch.setenv("RELAY_HOME", str(tmp_path / "home"))
    policy = RetryPolicy("vault")
    policy.failure()
    policy.failure()
    policy.failure()
    with pytest.raises(BackoffError):
        RetryPolicy("vault").check()
    policy.success()
    RetryPolicy("vault").check()
