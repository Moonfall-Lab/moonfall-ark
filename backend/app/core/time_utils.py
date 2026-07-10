from datetime import datetime, timezone
import time


def unix_ts() -> float:
    return time.time()


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
