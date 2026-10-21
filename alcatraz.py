"""Link Strike - the nightly ALCATRAZ room (pure schedule rules, no Flask, tested).

ALCATRAZ opens every day at 8pm Nigeria time (WAT = UTC+1, no daylight saving, so 19:00 UTC).
Once open it stays open until everybody has left. If nobody ever joins, it is closed again when
the night window ends. app.py runs the clock; this file only answers "is it ALCATRAZ night?".
"""
from datetime import datetime, timedelta, timezone

NAME = "ALCATRAZ"
OPEN_UTC_HOUR = 19      # 20:00 Nigeria time
WINDOW_H = 10           # an unjoined room is closed again 10 hours later (06:00 Nigeria time)
DEVICE = "system-alcatraz"   # owner of the reserved room name


def night(now=None):
    """The date (YYYY-MM-DD, UTC date the night started on) if `now` is inside tonight's window, else None."""
    now = now or datetime.now(timezone.utc)
    start = now - timedelta(hours=OPEN_UTC_HOUR)
    return start.date().isoformat() if start.hour < WINDOW_H else None
