"""
Shared date-input helpers for the legal guards (issues #55, #58).

Both DeadlineGuard and StatuteOfLimitationsGuard accept free-text dates.
dateutil parses numeric dates month-first by default, so a string like
"03/04/2026" verifies under one reading and refutes under the other with
no signal. The helper below detects that order ambiguity with a dual-parse
comparison; callers fail closed with an AMBIGUITY_NOTED trace step instead
of certifying one reading.
"""

import re

from dateutil.parser import parse as parse_date

# ISO year-leading dates ("2026-04-03", "2026/04/03") carry the year first
# and cannot swap month/day — excluded from ambiguity detection.
_YEAR_LEADING_RE = re.compile(r"^\s*\d{4}\s*[-/]")


def detect_order_ambiguity(raw: str) -> bool:
    """True when a date string reads differently month-first vs day-first.

    Returns False for ISO year-leading inputs, for inputs containing month
    names (both readings agree), and for unparseable inputs (those fail
    closed downstream at parse time, not here).
    """
    text = (raw or "").strip()
    if not text or _YEAR_LEADING_RE.match(text):
        return False
    try:
        month_first = parse_date(text)
    except Exception:
        return False
    try:
        day_first = parse_date(text, dayfirst=True)
    except Exception:
        return False
    return (month_first.year, month_first.month, month_first.day) != (
        day_first.year,
        day_first.month,
        day_first.day,
    )
