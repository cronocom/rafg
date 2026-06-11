"""Advisory file lock for the audit pipeline.

The audit pipeline begins with ``MATCH (n) DETACH DELETE n`` against the
sandbox. Two concurrent invocations on the same host racing for the same
Bolt URI would wipe each other's data mid-load and produce nonsense
verdicts. ``audit_lock`` makes the pipeline mutually exclusive on the
process level by holding an exclusive ``fcntl.flock`` for the duration of
the audit.

The lock is **advisory**: it only protects against other invocations of
this same CLI that also acquire the lock. Two separate auditor processes
running on different hosts that share the same Bolt URI can still race —
the only complete solution there is a per-audit Neo4j database, which is
an Enterprise-only feature. For local dev (the documented sandbox use
case) advisory locks are sufficient.

POSIX-only. Windows hosts (rare for this project, but possible) raise
``RuntimeError`` with a clear message so the user isn't left guessing.
"""

from __future__ import annotations

import contextlib
import errno
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AuditLockBusy(RuntimeError):
    """Another auditor process holds the lock on this reports directory."""


class AuditLockUnsupported(RuntimeError):
    """Advisory locking is not implemented for the current platform."""


@contextmanager
def audit_lock(reports_dir: Path) -> Iterator[Path]:
    """Acquire an exclusive advisory lock under ``reports_dir/.audit.lock``.

    Usage:
        with audit_lock(reports_dir):
            ... pipeline that writes to Neo4j ...

    Raises:
        AuditLockBusy: another audit holds the lock right now.
        AuditLockUnsupported: running on a platform without ``fcntl``.
        OSError: if ``reports_dir`` cannot be created.
    """
    if sys.platform == "win32":
        raise AuditLockUnsupported(
            "audit_lock requires POSIX fcntl; Windows is not supported in v0.x. "
            "Run the auditor inside WSL or a Linux container."
        )
    import fcntl

    reports_dir.mkdir(parents=True, exist_ok=True)
    lock_path = reports_dir / ".audit.lock"
    # Open in append mode so the file is created if missing and never
    # truncated. The locked region is the entire file (offset 0, len 0
    # under flock semantics = whole file).
    with open(lock_path, "a") as fh:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AuditLockBusy(
                f"another auditor process holds the lock at {lock_path}.\n"
                f"  Hint: only one audit can run at a time per reports/ "
                f"directory because every audit begins with `MATCH (n) "
                f"DETACH DELETE n` against Neo4j. Wait for the other run "
                f"to finish, or pass a different --reports-dir."
            ) from exc
        except OSError as exc:
            # EWOULDBLOCK is the BlockingIOError above; anything else is
            # an unexpected file-system error (permissions, network FS).
            if exc.errno == errno.EWOULDBLOCK:
                raise AuditLockBusy(str(exc)) from exc
            raise
        try:
            yield lock_path
        finally:
            # Best-effort unlock; the file close below releases it anyway,
            # so any OSError here is informational.
            with contextlib.suppress(OSError):
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
