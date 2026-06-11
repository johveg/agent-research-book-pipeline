#!/usr/bin/env python3
"""Non-disruptive self-healing watchdog for the book loop."""
from __future__ import annotations

import os
import stat
from pathlib import Path
from research_common import ROOT

WRAPPERS = [
    Path('/root/.hermes/scripts/terefohealreboa_book_start.sh'),
    Path('/root/.hermes/scripts/terefohealreboa_book_status.sh'),
    Path('/root/.hermes/scripts/terefohealreboa_book_watchdog.sh'),
]


def main() -> int:
    alerts=[]; repaired=[]
    if not ROOT.exists():
        print('ALERT: workspace missing:', ROOT); return 1
    for p in WRAPPERS:
        if p.exists() and not os.access(p, os.X_OK):
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
            repaired.append(f'executable bit restored: {p.name}')
        elif not p.exists():
            alerts.append(f'missing cron wrapper: {p}')
    # Never kill/restart LinkedIn browser here. Only alert if CDP likely absent.
    import socket
    s=socket.socket(); s.settimeout(1)
    try:
        s.connect(('127.0.0.1',9222))
    except Exception:
        alerts.append('LinkedIn CDP port 9222 is not reachable; human/session check may be needed')
    finally:
        s.close()
    if repaired: print('Repaired: ' + '; '.join(repaired))
    if alerts:
        print('ALERT: ' + '; '.join(alerts)); return 1
    return 0
if __name__=='__main__': raise SystemExit(main())
