"""Run the private audit worker; never prints input, source paths or exceptions."""
import argparse
import signal
import sys
from pathlib import Path
from threading import Event
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))


def main():
    parser = argparse.ArgumentParser(description='Private emergency report processing worker')
    parser.add_argument('--once', action='store_true', help='Attempt one queued job and exit')
    args = parser.parse_args()
    from app.emergency_audit_worker import process_one
    from app.department_maintenance import MaintenanceUnavailable
    stop = Event(); identity = str(uuid4())
    def end(*_): stop.set()
    signal.signal(signal.SIGINT, end); signal.signal(signal.SIGTERM, end)
    while not stop.is_set():
        try:
            processed = process_one(worker_id=identity)
        except MaintenanceUnavailable:
            processed = False
        except Exception:
            # Operational details belong in the protected admin status, not
            # service logs. A failed claim stays queued/leased for recovery.
            print('EMERGENCY_AUDIT_WORKER_UNAVAILABLE', file=sys.stderr)
            if args.once: return 1
            processed = False
        if args.once: return 0
        if not processed: stop.wait(3)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
