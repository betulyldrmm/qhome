"""Time zones for QHome: IANA names with daylight saving when the zone database is
available, fixed offsets ("UTC+3", "UTC+5:30") always. Standard library only."""
import re
import time
from datetime import datetime, timedelta, timezone

try:
    import zoneinfo
except ImportError:            # Python 3.8
    zoneinfo = None

DEFAULT = "Europe/Istanbul"
FIXED_RE = re.compile(r"^UTC(?:([+-])(\d{1,2})(?::(00|15|30|45))?)?$")
IANA_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+){1,2}$")
_SKIP = ("Etc/", "posix/", "right/", "SystemV/")
# Standard offset in minutes for common zones, used only when the database is missing.
STD_OFFSET = {"Europe/Istanbul": 180, "Europe/London": 0, "Europe/Berlin": 60, "Europe/Paris": 60,
              "Europe/Moscow": 180, "America/New_York": -300, "America/Chicago": -360,
              "America/Denver": -420, "America/Los_Angeles": -480, "America/Sao_Paulo": -180,
              "Asia/Dubai": 240, "Asia/Kolkata": 330, "Asia/Shanghai": 480, "Asia/Tokyo": 540,
              "Australia/Sydney": 600, "Pacific/Auckland": 720}
_zones = None


def fixed_name(minutes):
    """180 -> 'UTC+3', 330 -> 'UTC+5:30', 0 -> 'UTC'."""
    minutes = int(round(minutes))
    if minutes == 0:
        return "UTC"
    h, m = divmod(abs(minutes), 60)
    return "UTC%s%d%s" % ("+" if minutes > 0 else "-", h, ":%02d" % m if m else "")


def from_offset(hours):
    """Old device.tz_offset (hours, may be fractional) -> new device.tz."""
    try:
        minutes = int(round(float(hours) * 4)) * 15
    except (TypeError, ValueError):
        return DEFAULT
    return fixed_name(max(-720, min(840, minutes)))


def fixed_minutes(name):
    """Offset in minutes of a fixed name, or None when it is not one (or out of range)."""
    m = FIXED_RE.match(str(name or ""))
    if not m:
        return None
    if not m.group(1):
        return 0
    minutes = int(m.group(2)) * 60 + int(m.group(3) or 0)
    minutes = -minutes if m.group(1) == "-" else minutes
    return minutes if -720 <= minutes <= 840 else None


def fixed_names():
    out = [fixed_name(m) for m in range(-720, 841, 30)]
    for extra in (345, 525, 765):          # Nepal, Eucla, Chatham
        out.append(fixed_name(extra))
    return sorted(set(out), key=fixed_minutes)


def zones():
    """Sorted IANA names for the dropdown; empty when this computer has no zone database."""
    global _zones
    if _zones is None:
        names = set()
        if zoneinfo is not None:
            try:
                names = zoneinfo.available_timezones()
            except Exception:
                names = set()
        _zones = sorted(n for n in names if "/" in n and not n.startswith(_SKIP))
    return _zones


def _load(name):
    if zoneinfo is None or not IANA_RE.match(str(name or "")):
        return None
    try:
        return zoneinfo.ZoneInfo(name)
    except Exception:           # ZoneInfoNotFoundError, ValueError, OSError
        return None


def valid(name):
    if not isinstance(name, str):
        return False
    if fixed_minutes(name) is not None:
        return True
    if _load(name) is not None:
        return True
    # No database here (for example Windows without the tzdata package): accept any
    # well-formed name so a setup saved on the board can still be loaded on a PC.
    return isinstance(name, str) and bool(IANA_RE.match(name)) and (not zones() or name in STD_OFFSET)


def resolve(name):
    """-> (tzinfo, exact). exact is False when a named zone had to be replaced by a
    fixed offset because the zone database is missing (no daylight saving then)."""
    if not isinstance(name, str):          # a hand-edited config file
        name = ""
    minutes = fixed_minutes(name)
    if minutes is not None:
        return timezone(timedelta(minutes=minutes), fixed_name(minutes)), True
    tz = _load(name)
    if tz is not None:
        return tz, True
    minutes = STD_OFFSET.get(name, 0)
    return timezone(timedelta(minutes=minutes), fixed_name(minutes)), False


def now(name, epoch=None):
    tz, _ = resolve(name)
    return datetime.fromtimestamp(time.time() if epoch is None else epoch, tz)


def describe(name, epoch=None):
    """What the web UI needs to show a live clock."""
    epoch = time.time() if epoch is None else epoch
    tz, exact = resolve(name)
    dt = datetime.fromtimestamp(epoch, tz)
    off = dt.utcoffset() or timedelta(0)
    return {"tz": name, "epoch": round(epoch, 3), "offset": int(off.total_seconds() // 60),
            "label": fixed_name(off.total_seconds() / 60), "abbr": dt.tzname() or "",
            "dst": bool(dt.dst()), "exact": exact, "local": dt.strftime("%Y-%m-%dT%H:%M:%S")}
