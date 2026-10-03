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
from datetime import datetime

from dateutil.parser import parse as parse_date

# ISO year-leading dates ("2026-04-03", "2026/04/03") carry the year first
# and cannot swap month/day — excluded from ambiguity detection.
_YEAR_LEADING_RE = re.compile(r"^\s*\d{4}\s*[-/]")

# Dual-sentinel defaults for completeness checks (issues #57, #59): the two
# defaults differ in every date component, so any component dateutil fills
# from the wall clock surfaces as a divergence. Time-of-day is excluded
# from the comparison — a supplied time ("2026-01-15 23:00") is complete.
_SENTINEL_A = datetime(2000, 1, 1)
_SENTINEL_B = datetime(1999, 12, 31)


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


def detect_incomplete_date(raw: str) -> bool:
    """True when dateutil would fill any date component from the wall clock.

    Parses under two sentinel defaults differing in year, month, and day;
    divergence means the input left a component unspecified ("March 2024",
    "Friday", "23:00"). A date that parses under only one sentinel is also
    incomplete — e.g. yearless "February 29" parses under the leap default
    but not the non-leap one, and would otherwise take its year from the
    run-year clock. Comparison is date-only so supplied times of day do
    not count as incomplete. Returns False for unparseable inputs — those
    fail closed downstream at parse time, not here.
    """
    text = (raw or "").strip()
    if not text:
        return False
    try:
        under_a = parse_date(text, default=_SENTINEL_A)
    except Exception:
        under_a = None
    try:
        under_b = parse_date(text, default=_SENTINEL_B)
    except Exception:
        under_b = None
    if (under_a is None) != (under_b is None):
        return True
    if under_a is None:
        return False
    return (under_a.year, under_a.month, under_a.day) != (
        under_b.year,
        under_b.month,
        under_b.day,
    )
