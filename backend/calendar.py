from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

BERLIN = ZoneInfo("Europe/Berlin")
NEW_YORK = ZoneInfo("America/New_York")


def phase(db, at=None):
    at = at or datetime.now(timezone.utc)
    if at.tzinfo is None:
        raise ValueError("Zeitzone erforderlich")
    local = at.astimezone(BERLIN)
    day = local.date().isoformat()
    record = db.one("SELECT * FROM sessions WHERE date=?", (day,))
    result = dict(local_at=local.isoformat(), date=day, opens_at=None, closes_at=None,
                  trading=False, liquidating=False, exchange_open=False, source="Alpaca calendar")
    if local.time() >= time(19):
        return result | dict(phase="stopped", reason="Tagesende 19:00 Europe/Berlin")
    if local.time() < time(7, 30):
        return result | dict(phase="sleeping", reason="Betriebsbeginn 07:30 Europe/Berlin")
    if not record:
        # Absence alone cannot distinguish holiday from missing permissions/cache.
        covered = db.get("calendar_coverage", {})
        known = covered.get("start", "9999") <= day <= covered.get("end", "0000")
        return result | dict(phase="closed" if known else "calendar_missing",
                             reason="Börsenfeiertag/Wochenende" if known else "Kein bestätigter Alpaca-Börsenkalender; Handel gesperrt")
    opens = datetime.fromisoformat(record["opens_at"])
    closes = datetime.fromisoformat(record["closes_at"])
    cutoff = min(closes, datetime.combine(local.date(), time(18, 25), BERLIN))
    stop = min(closes, datetime.combine(local.date(), time(18, 30), BERLIN))
    result |= dict(opens_at=opens.astimezone(BERLIN).isoformat(), closes_at=closes.astimezone(BERLIN).isoformat(),
                   exchange_open=opens <= at < closes)
    if at < opens:
        return result | dict(phase="preparing", reason="Research vor Börsenöffnung")
    if at < cutoff:
        return result | dict(phase="trading", trading=True, reason="Reguläre erlaubte Handelszeit")
    if at < stop:
        return result | dict(phase="liquidating", liquidating=True, reason="Nur kontrollierte Positionsschließungen")
    return result | dict(phase="review", reason="Keine neuen Orders; Tagesauswertung")
