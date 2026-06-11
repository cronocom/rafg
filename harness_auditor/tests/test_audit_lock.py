"""Tests for ``_audit_lock.audit_lock``.

The lock guards the audit pipeline against concurrent invocations on the
same host. These tests verify the contract:

  * Acquiring the lock when nobody holds it works and the context
    manager yields the lock path.
  * A second acquire while the first is held raises ``AuditLockBusy``.
  * Releasing the lock allows a subsequent acquire to succeed.

POSIX-only: ``fcntl.flock`` is the underlying primitive. The tests are
skipped on Windows so the suite still passes there (though the auditor
itself emits a yellow warning on that platform).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from harness_auditor._audit_lock import AuditLockBusy, audit_lock

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="advisory locks require POSIX fcntl; not implemented on Windows.",
)


def test_lock_is_acquirable(tmp_path: Path) -> None:
    with audit_lock(tmp_path) as lock_path:
        assert lock_path.exists()
        assert lock_path.name == ".audit.lock"


def test_lock_is_released_after_context_exits(tmp_path: Path) -> None:
    """A second acquire after the first context closes must succeed."""
    with audit_lock(tmp_path):
        pass
    with audit_lock(tmp_path) as lock_path:
        assert lock_path.exists()


def test_second_acquire_while_held_raises_busy(tmp_path: Path) -> None:
    """Concurrency contract: only one auditor at a time per reports_dir.

    We hold the first lock open inside the ``with`` block and try to
    acquire a second time. ``BlockingIOError`` from ``fcntl.flock``
    surfaces as ``AuditLockBusy`` with a hint pointing at the lock path.
    """
    with audit_lock(tmp_path), pytest.raises(AuditLockBusy) as ei, audit_lock(tmp_path):
        pytest.fail("should have raised AuditLockBusy")
    # The diagnostic must name the lock file and the offending operation.
    message = str(ei.value)
    assert ".audit.lock" in message
    assert "DETACH DELETE" in message  # the explanation of why locking matters


def test_lock_creates_reports_dir_if_missing(tmp_path: Path) -> None:
    """``reports_dir`` is auto-created so a first audit does not need
    pre-existing infrastructure."""
    target = tmp_path / "subdir" / "reports"
    assert not target.exists()
    with audit_lock(target):
        assert target.is_dir()
        assert (target / ".audit.lock").exists()
