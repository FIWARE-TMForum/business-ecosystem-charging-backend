import datetime
import re


def to_utc_z(dt):
    if isinstance(dt, datetime.datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    if isinstance(dt, datetime.date):
        dt = datetime.datetime(dt.year, dt.month, dt.day, tzinfo=datetime.timezone.utc)
        return dt.isoformat().replace("+00:00", "Z")
    raise TypeError(f"Expected datetime or date, got {type(dt).__name__}")


def utc_z_to_dt(dt_str: str) -> datetime.datetime:
    normalized = re.sub(r'(\.\d{6})\d+', r'\1', dt_str.replace("Z", "+00:00"))
    return datetime.datetime.fromisoformat(normalized)
