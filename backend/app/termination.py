"""Portable process-termination guard for cleanup-sensitive command line tools."""
from contextlib import contextmanager
import signal


@contextmanager
def controlled_termination():
    previous = signal.getsignal(signal.SIGTERM)

    def terminate(signum, frame):
        # Allow cleanup finally blocks to finish even when another stop request arrives.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise SystemExit(128 + signum)

    signal.signal(signal.SIGTERM, terminate)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous)
