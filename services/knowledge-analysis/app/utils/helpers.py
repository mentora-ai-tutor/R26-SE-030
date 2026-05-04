from datetime import datetime


def utc_now_iso() -> str:
    return datetime.utcnow().isoformat()
