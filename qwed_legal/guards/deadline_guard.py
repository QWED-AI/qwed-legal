"""
DeadlineGuard: Verify date calculations in legal contracts.

Handles business days, calendar days, leap years, and holiday exclusions.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
import re

from dateutil.parser import parse as parse_date
from dateutil.relativedelta import relativedelta
import holidays

from qwed_legal.diagnostics import LegalDiagnosticsMixin, LegalDiagnosticStatus
from qwed_legal.dates import detect_order_ambiguity, detect_incomplete_date
from qwed_legal.models import (
    VerificationStep,
    STEP_RULE_IDENTIFIED,
    STEP_AMBIGUITY_NOTED,
    STEP_FACT_DERIVED,
    STEP_CONCLUSION,
    EVIDENCE_DETERMINISTIC,
    EVIDENCE_PARSED,
    EVIDENCE_UNSUPPORTED,
)


@dataclass(frozen=True)
class DeadlineResult(LegalDiagnosticsMixin):
    """Result of deadline verification."""
    verified: bool
    signing_date: Optional[datetime]
    claimed_deadline: Optional[datetime]
    computed_deadline: Optional[datetime]
    term_parsed: str
    difference_days: Optional[int]
    message: str
    is_computable: bool = True  # False if term is ambiguous/unparseable
    verification_mode: str = "SYMBOLIC"  # Always SYMBOLIC for legal (SymPy/Z3)
    verification_trace: list = field(default_factory=list)

    def __post_init__(self):
        self._freeze_evidence_fields("verification_trace")

    def _diagnostic_status(self):
        if not self.is_computable:
            return LegalDiagnosticStatus.UNVERIFIABLE
        if self.verified:
            return LegalDiagnosticStatus.VERIFIED
        return LegalDiagnosticStatus.BLOCKED


class DeadlineGuard:
    """
    Verify date calculations in legal contracts.
    
    Catches common LLM errors like:
    - Confusing business days vs calendar days
    - Leap year miscalculations
    - Weekend/holiday exclusion errors
    
    Example:
        >>> guard = DeadlineGuard()
        >>> result = guard.verify("2026-01-15", "30 business days", "2026-02-14")
        >>> print(result.verified)  # False - 30 business days != Feb 14
    """
    
    def __init__(self, country: str = "US", state: Optional[str] = None):
        """
        Initialize DeadlineGuard.
        
        Args:
            country: ISO country code for holidays (default: US)
            state: State/province code for regional holidays (optional)
        """
        self.country = country
        self.state = state
        # Track whether the requested holiday calendar was actually built.
        # QWED principle: no silent degradation. If we fall back to a different
        # calendar, business-day computations must not be presented as proven.
        self.holiday_calendar_valid = True
        self.holiday_fallback_reason = None
        try:
            self.holiday_calendar = holidays.country_holidays(country, subdiv=state)
        except Exception as e:
            self.holiday_calendar = holidays.US()
            self.holiday_calendar_valid = False
            self.holiday_fallback_reason = (
                f"Could not build holiday calendar for country={country!r}, "
                f"state={state!r}: {e}. Fell back to US() calendar."
            )
    
    def verify(
        self,
        signing_date: str,
        term: str,
        claimed_deadline: str,
        tolerance_days: int = 0
    ) -> DeadlineResult:
        """
        Verify a deadline calculation.
        
        Args:
            signing_date: The date the contract was signed (ISO format or natural language)
            term: The term description (e.g., "30 days", "30 business days", "2 weeks")
            claimed_deadline: The deadline claimed by the LLM
            tolerance_days: Allow +/- this many days for verification (default: 0)
        
        Returns:
            DeadlineResult with verification status and computed deadline
        """
        # Parse dates
        try:
            signing = parse_date(signing_date)
            claimed = parse_date(claimed_deadline)
        except Exception as e:
            return DeadlineResult(
                verified=False,
                signing_date=None,
                claimed_deadline=None,
                computed_deadline=None,
                term_parsed="ERROR",
                difference_days=None,
                message=f"Failed to parse dates: {e}",
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Date parsing failed — cannot proceed.",
                        inputs={
                            "signing_date": signing_date,
                            "claimed_deadline": claimed_deadline,
                        },
                        output=f"UNSUPPORTED: parse error: {e}",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )
        
        # Fail-closed on order-ambiguous numeric dates (issue #55):
        # "03/04/2026" verifies under month-first and refutes under day-first
        # with no signal. Detect the dual reading and refuse to certify
        # either one. Raw strings are preserved in the trace for auditability.
        ambiguous_fields = [
            label
            for label, raw in (
                ("signing_date", signing_date),
                ("claimed_deadline", claimed_deadline),
            )
            if detect_order_ambiguity(raw)
        ]
        if ambiguous_fields:
            # Parsed datetimes are recorded as None: a yearless input like
            # "03/04" reaches this gate with its year from the clock, and
            # returning it would show different dates on different runs.
            # Raw strings stay in the trace below.
            return DeadlineResult(
                verified=False,
                signing_date=None,
                claimed_deadline=None,
                computed_deadline=None,
                term_parsed=term,
                difference_days=None,
                message=(
                    f"⚠️ UNVERIFIABLE: {', '.join(ambiguous_fields)} "
                    f"is order-ambiguous (reads differently month-first vs "
                    f"day-first). Supply an ISO year-leading date "
                    f"(YYYY-MM-DD) or an unambiguous written date."
                ),
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Checked date inputs for month/day order ambiguity.",
                        inputs={
                            "signing_date": signing_date,
                            "claimed_deadline": claimed_deadline,
                        },
                        output=(
                            "AMBIGUITY NOTED: order-ambiguous input(s): "
                            + ", ".join(ambiguous_fields)
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                    VerificationStep(
                        step=STEP_AMBIGUITY_NOTED,
                        description="Refused to certify either reading of the ambiguous date.",
                        inputs={
                            "ambiguous_fields": ambiguous_fields,
                            "signing_date": signing_date,
                            "claimed_deadline": claimed_deadline,
                        },
                        output="UNSUPPORTED: order-ambiguous date — no deterministic reading.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                ],
            )

        # Fail-closed on wall-clock-completed partial dates (issue #57):
        # "March 2024" or "Friday" silently fill missing components from
        # the run day, so identical inputs verify opposite verdicts on
        # different days. Refuse partial dates outright.
        incomplete_fields = [
            label
            for label, raw in (
                ("signing_date", signing_date),
                ("claimed_deadline", claimed_deadline),
            )
            if detect_incomplete_date(raw)
        ]
        if incomplete_fields:
            return DeadlineResult(
                verified=False,
                signing_date=None,
                claimed_deadline=None,
                computed_deadline=None,
                term_parsed=term,
                difference_days=None,
                message=(
                    f"⚠️ UNVERIFIABLE: {', '.join(incomplete_fields)} "
                    f"is a partial date — missing components would be "
                    f"completed from the system clock, making the verdict "
                    f"a function of the run day. Supply a complete date "
                    f"(YYYY-MM-DD)."
                ),
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Checked date inputs for wall-clock completion.",
                        inputs={
                            "signing_date": signing_date,
                            "claimed_deadline": claimed_deadline,
                        },
                        output=(
                            "AMBIGUITY NOTED: partial date(s): "
                            + ", ".join(incomplete_fields)
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                    VerificationStep(
                        step=STEP_AMBIGUITY_NOTED,
                        description="Refused to complete partial dates from the system clock.",
                        inputs={
                            "incomplete_fields": incomplete_fields,
                            "signing_date": signing_date,
                            "claimed_deadline": claimed_deadline,
                        },
                        output="UNSUPPORTED: partial date — components would come from the run day.",
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    ),
                ],
            )

        # Fail-closed on event-anchored terms (issue #54): a term like
        # "within 15 days after receipt of written notice" carries a valid
        # quantity/unit pair but anchors it to an event, not the signing
        # date. Computing from signing certifies deadlines anchored to an
        # unknowable date (chosen-date forgery: any target is certifiable).
        # Runs BEFORE date arithmetic so rejected business-day terms never
        # iterate the holiday calendar.
        anchor = self._event_anchor(term.lower())
        if anchor:
            return DeadlineResult(
                verified=False,
                signing_date=signing,
                claimed_deadline=claimed,
                computed_deadline=None,
                term_parsed=term,
                difference_days=None,
                message=(
                    f"⚠️ UNVERIFIABLE: Term '{term}' is anchored to an "
                    f"event ('{anchor}'), not to the "
                    f"signing date. The real deadline is unknowable from "
                    f"these inputs — supply the anchor event's date."
                ),
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Checked term for event anchors before computing from signing date.",
                        inputs={"term": term},
                        output=(
                            "UNSUPPORTED: event-anchored term — anchor "
                            f"'{anchor}' has no supplied date."
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        # Parse term and calculate deadline
        computed, used_business_days = self._calculate_deadline(signing, term)

        # Fail-closed: if the term is ambiguous, do not verify
        if computed is None:
            return DeadlineResult(
                verified=False,
                signing_date=signing,
                claimed_deadline=claimed,
                computed_deadline=None,
                term_parsed=term,
                difference_days=None,
                message=(
                    f"⚠️ UNVERIFIABLE: Term '{term}' does not contain exactly "
                    f"one provable time quantity and unit within the "
                    f"supported range. Cannot compute a deterministic "
                    f"deadline. Compound terms (e.g., '30 days and 2 "
                    f"months'), quantities beyond the supported range, and "
                    f"ambiguous legal language (e.g., 'reasonable period', "
                    f"'promptly') require human legal interpretation."
                ),
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Term parsed for exactly one deterministic time quantity and unit.",
                        inputs={"term": term},
                        output=(
                            "UNSUPPORTED: ambiguous term — no provable "
                            "quantity/unit, or multiple conflicting time "
                            "expressions."
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        # Fail-closed on mixed timezone-aware/naive inputs (statute
        # parity): the frames are incomparable, so even date-granularity
        # comparison would silently mix calendar days.
        if (claimed.tzinfo is None) != (computed.tzinfo is None):
            return DeadlineResult(
                verified=False,
                signing_date=signing,
                claimed_deadline=claimed,
                computed_deadline=None,
                term_parsed=term,
                difference_days=None,
                message=(
                    "⚠️ UNVERIFIABLE: Mixed timezone inputs — one date is "
                    "timezone-aware and the other is timezone-naive. "
                    "Supply both dates with or both without a timezone."
                ),
                is_computable=False,
                verification_trace=[
                    VerificationStep(
                        step=STEP_RULE_IDENTIFIED,
                        description="Validated timezone consistency between signing and claimed dates.",
                        inputs={
                            "signing_date": str(signing),
                            "claimed_deadline": str(claimed),
                        },
                        output=(
                            "UNSUPPORTED: mixed timezone-aware and "
                            "timezone-naive inputs — cannot compare."
                        ),
                        evidence_type=EVIDENCE_UNSUPPORTED,
                    )
                ],
            )

        # Compare at the declared date granularity (issue #56); see
        # _comparison_days for the timezone rules.
        claimed_day, computed_day = self._comparison_days(claimed, computed)
        diff = abs((claimed_day - computed_day).days)
        verified = diff <= tolerance_days

        # QWED: if business days were used but the requested holiday calendar
        # could not be built, the computation may rest on the wrong calendar.
        # Do not present such a result as deterministic proof — fail closed.
        calendar_unreliable = used_business_days and not self.holiday_calendar_valid
        compute_evidence = (
            EVIDENCE_UNSUPPORTED if calendar_unreliable else EVIDENCE_DETERMINISTIC
        )

        if calendar_unreliable:
            verified = False
            message = (
                "⚠️ UNVERIFIABLE: This deadline uses business days, but the "
                f"requested holiday calendar could not be built. "
                f"{self.holiday_fallback_reason} Business-day results cannot be "
                "proven against the wrong calendar."
            )
        elif verified:
            message = "✅ VERIFIED: Deadline calculation is correct."
        else:
            message = self._mismatch_message(claimed, claimed_day, computed_day, diff)

        if calendar_unreliable:
            conclusion_output = "UNSUPPORTED: business-day calendar unavailable"
        elif verified:
            conclusion_output = "DEADLINE VERIFIED"
        else:
            conclusion_output = "DEADLINE MISMATCH"

        trace = [
            VerificationStep(
                step=STEP_RULE_IDENTIFIED,
                description="Parsed term into a deterministic time quantity and unit.",
                inputs={"term": term, "tolerance_days": tolerance_days},
                output=f"Parsed term: '{term}'",
                evidence_type=EVIDENCE_PARSED,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Computed deadline from signing date and parsed term.",
                inputs={
                    "signing_date": str(signing),
                    "term": term,
                    "used_business_days": used_business_days,
                    "holiday_calendar_valid": self.holiday_calendar_valid,
                },
                output=f"Computed deadline: {computed.strftime('%Y-%m-%d')}",
                evidence_type=compute_evidence,
            ),
            VerificationStep(
                step=STEP_FACT_DERIVED,
                description="Computed difference between claimed and computed deadline.",
                inputs={
                    "claimed_deadline": str(claimed),
                    "computed_deadline": str(computed),
                    "tolerance_days": tolerance_days,
                },
                output=f"Difference: {diff} day(s)",
                evidence_type=compute_evidence,
            ),
            VerificationStep(
                step=STEP_CONCLUSION,
                description="Determined whether the claimed deadline matches within tolerance.",
                inputs={
                    "difference_days": diff,
                    "tolerance_days": tolerance_days,
                    "calendar_unreliable": calendar_unreliable,
                },
                output=conclusion_output,
                evidence_type=compute_evidence,
            ),
        ]

        return DeadlineResult(
            verified=verified,
            signing_date=signing,
            claimed_deadline=claimed,
            computed_deadline=computed,
            term_parsed=term,
            difference_days=diff,
            message=message,
            is_computable=not calendar_unreliable,
            verification_trace=trace,
        )
    
    # A time expression pairs a number with its immediately adjacent unit.
    # Positional pairing prevents compound terms like "30 days and 2 months"
    # from combining the first number in the term with the last matching
    # unit branch (issue #39). The lookbehind requires a token boundary
    # before the number, so decimals ("1.5 years"), signed values
    # ("-30 days"), and numbers embedded in words ("section30days") are
    # never matched partially as a shorter suffix quantity.
    _TIME_EXPRESSION_RE = re.compile(
        r"(?<![\w.,+-])(\d+)\s*(business\s+|working\s+|work\s+)?"
        r"(?:calendar\s+)?(days?|weeks?|months?|years?)\b"
    )
    # Any numeric token in the term, integer or decimal ("4.2", "1,000").
    _ANY_NUMBER_RE = re.compile(r"\d+(?:[.,]\d+)*")
    # Event anchors that re-anchor a term away from the signing date
    # (issue #54). Only a preposition-governed event noun counts as an
    # anchor ("after receipt", "within 15 days of payment") — a bare
    # mention ("30 days from signing to deliver notice") leaves the
    # signing anchor intact. Up to two intervening words allow adjectives
    # ("after written notice"); the "the date (the|of)" alternative covers
    # phrasings like "after the date the notice is received" without
    # widening the general gap (which would catch signing-anchored text).
    # "of" only counts directly after a time unit ("30 days of payment",
    # "within 30 days of delivery"): a bare "of" also matches descriptive
    # phrases ("notice of termination", "provision of services") where the
    # first noun is the obligation, not a temporal anchor. Deliberately
    # excludes signing-adjacent nouns ("signing", "execution") and generic
    # "event" ("in the event of" is conditional, not a temporal anchor).
    _EVENT_ANCHOR_RE = re.compile(
        r"\b(?:after|following|upon|on|from|within|(?:day|days|week|weeks|month|months|year|years)\s+of)\s+"
        r"(?:(?:[a-z]+\s+){0,2}?|the\s+date\s+(?:the\s+|of\s+))"
        r"(receipts?|notices?|services?|deliver(?:y|ies)|occurrences?|demands?|"
        r"invoices?|breach(?:es)?|terminations?|payments?|acceptances?|approval(?:s)?)\b"
    )
    # Signing anchors ("from signing", "date of signing"): a signing anchor
    # ahead of an event anchor keeps the signing computation only when the
    # event is conditional wording ("conditioned upon acceptance"). A plain
    # later event anchor ("or after delivery", "period begins upon
    # receipt") re-anchors the period and fails closed.
    _SIGNING_ANCHOR_RE = re.compile(
        r"\b(?:after|following|upon|from|within|of)\s+(?:the\s+)?(?:signing|execution)\b"
    )
    # Conditional-event wording names an event without anchoring the
    # period to it ("conditioned upon acceptance", "subject to approval"):
    # such phrases are conditions on the obligation, not temporal anchors.
    # Checked against the text preceding each event match.
    _CONDITIONAL_EVENT_RE = re.compile(
        r"\b(?:(?:conditioned|conditional|contingent|dependent)\s+(?:up)?on|subject\s+to)\s+(?:[a-z]+\s+){0,2}$"
    )
    # Nouns that can name a condition rather than a temporal anchor:
    # agentive acts ("acceptance", "approval", "payment") are things a
    # party does, so conditional wording around them reads as conditionality.
    # Temporal occurrences ("receipt", "delivery", "breach", ...) always
    # anchor — conditional wording around them does not waive the unknown
    # date. Intentionally narrow: fail-closed default.
    _CONDITIONABLE_NOUNS = frozenset(
        {
            "acceptance", "acceptances",
            "approval", "approvals",
            "payment", "payments",
        }
    )
    # Explicit start-date language defeats any conditional reading — but
    # only inside the event's own comma/semicolon segment, and only when
    # linked to the event by a dependent-phrase ("start date dependent on
    # acceptance", "commencement is dependent on payment"). A bare
    # "commencement of services" describes what commences, not when the
    # stated period starts. Parentheses do not split: wording like "the
    # start date (as defined herein) dependent on acceptance" still
    # governs its event, while a parenthetical clarification ("(start
    # date is signing)") is split off by its comma.
    _START_DATE_RE = re.compile(
        r"\b(?:start|commencement|effective)(?:\s+date)?\s+"
        r"(?:is\s+|are\s+|was\s+|were\s+)?depend(?:ent|s|ed|ing)?\s+on\b"
    )

    @staticmethod
    def _start_date_governs(term_lower: str, pos: int) -> bool:
        """Start-date language inside the event's own comma/semicolon segment.

        Parentheticals are stripped before matching: an interruption
        ("the start date (as defined herein) dependent on acceptance")
        still governs, while a sealed clarification ("(start date is
        signing)") vanishes with its parens. Segments split on commas
        and semicolons only.
        """
        bounds = [0] + [m.end() for m in re.finditer(r"[,;]", term_lower)]
        bounds.append(len(term_lower))
        seg_start = max(b for b in bounds if b <= pos)
        seg_end = min(b for b in bounds if b > pos)
        # Strip parentheticals first: an interruption ("the start date (as
        # defined herein) dependent on ...") must not break the link, while
        # a clarification sealed in parens ("(start date is signing)")
        # vanishes with them.
        seg_text = re.sub(r"\([^)]*\)", " ", term_lower[seg_start:seg_end])
        return DeadlineGuard._START_DATE_RE.search(seg_text) is not None

    @staticmethod
    def _event_anchor(term_lower: str) -> "Optional[str]":
        """Event noun anchoring the term's period, or None.

        Scans every event match in order: a match preceded by a signing
        anchor is skipped only when conditional wording governs a
        conditionable noun ("conditioned upon acceptance") and no
        same-segment start-date language re-anchors the period. A plain
        later event anchor ("or after delivery", "period begins upon
        receipt"), conditional wording around a temporal noun ("dependent
        on receipt"), or an explicit start-date event ("start date
        dependent on acceptance") re-anchors the period and fails closed.
        Returns the matched event noun for messaging.
        """
        signing_match = DeadlineGuard._SIGNING_ANCHOR_RE.search(term_lower)
        for event_match in DeadlineGuard._EVENT_ANCHOR_RE.finditer(term_lower):
            prefix = term_lower[: event_match.start(1)]
            if (
                signing_match is not None
                and signing_match.start() < event_match.start()
                and DeadlineGuard._CONDITIONAL_EVENT_RE.search(prefix)
                and event_match.group(1).lower() in DeadlineGuard._CONDITIONABLE_NOUNS
                and not DeadlineGuard._start_date_governs(
                    term_lower, event_match.start(1)
                )
            ):
                continue
            return event_match.group(1)
        return None

    # No legal deadline spans this magnitude (~274 years). Bounding the
    # parsed quantity bounds both date arithmetic and the business-day
    # iteration loop (issue #42: unhandled OverflowError / unbounded loop).
    _MAX_TERM_QUANTITY = 100_000

    @staticmethod
    def _mismatch_message(claimed: datetime, claimed_day, computed_day, diff: int) -> str:
        """Mismatch text that cannot contradict its own difference.

        Reports the compared calendar days (never identical dates beside
        a non-zero difference). When conversion moved the claim across
        midnight, both spellings are shown so the caller's original claim
        still matches what wrappers display beside this message.
        """
        claimed_raw = claimed.strftime("%Y-%m-%d")
        claimed_shown = claimed_day.isoformat()
        if claimed_shown != claimed_raw:
            claimed_shown = (
                f"{claimed_raw} (={claimed_shown} in the deadline's timezone)"
            )
        return (
            f"❌ ERROR: Deadline mismatch. "
            f"Expected {computed_day.isoformat()}, "
            f"but LLM claimed {claimed_shown}. "
            f"Difference: {diff} days."
        )

    @staticmethod
    def _comparison_days(claimed: datetime, computed: datetime):
        """Calendar days for date-granularity comparison (issue #56).

        Both-aware inputs compare in the computed deadline's timezone, so
        the same moment in different offsets is not a false mismatch while
        the deadline's calendar-day meaning is preserved. Anything else
        compares naive calendar dates (.date() never subtracts datetimes,
        so mixed aware/naive inputs cannot raise here).
        """
        if claimed.tzinfo is not None and computed.tzinfo is not None:
            return claimed.astimezone(computed.tzinfo).date(), computed.date()
        return claimed.date(), computed.date()

    def _calculate_deadline(
        self, start_date: datetime, term: str
    ) -> "tuple[Optional[datetime], bool]":
        """Calculate the actual deadline from a term description.

        Returns a tuple of (deadline, used_business_days). deadline is None if
        the term is ambiguous and cannot be parsed into a single deterministic
        deadline (fail-closed); used_business_days indicates whether the
        holiday calendar was relied upon.
        """
        term_lower = term.lower().strip()
        expression = self._match_single_expression(term_lower)
        if expression is None:
            return None, False

        num_str, business_qualifier, unit = expression
        # Fail-closed digit-length bound (#80): CPython caps int() string
        # conversion at 4300 digits, so bound the run before coercion — the
        # _MAX_TERM_QUANTITY range cap below cannot run until int() succeeds.
        # No legal term needs >18 digits.
        if len(num_str) > 18:
            return None, False
        return self._compute_from_expression(
            start_date, int(num_str), bool(business_qualifier), unit
        )

    def _match_single_expression(self, term_lower: str) -> "Optional[tuple]":
        """Find the single number-unit expression in a term, or None.

        Fails closed when the term contains no number-unit pair, more
        than one pair (compound legal term — which quantities combine is
        a legal interpretation, not a deterministic computation), or a
        numeric token that is not part of the pair ("30 or 60 days",
        "30 days and 48 hours", a clause reference like "4.2").
        """
        expressions = self._TIME_EXPRESSION_RE.findall(term_lower)
        if not expressions or len(expressions) > 1:
            return None

        num_str = expressions[0][0]

        # Every numeric token in the term must be the paired quantity.
        # An unmatched number leaves the term ambiguous — the guard
        # cannot prove which quantity applies, so fail closed.
        all_numbers = self._ANY_NUMBER_RE.findall(term_lower)
        if len(all_numbers) != 1 or all_numbers[0] != num_str:
            return None

        return expressions[0]

    def _compute_from_expression(
        self, start_date: datetime, num: int, is_business_days: bool, unit: str
    ) -> "tuple[Optional[datetime], bool]":
        """Compute the deadline from a validated single expression."""
        # Fail-closed: quantity beyond the supported range
        if num > self._MAX_TERM_QUANTITY:
            return None, False

        # "business months" / "working years" have no deterministic
        # calendar meaning — fail closed rather than silently computing
        # calendar months/years.
        if is_business_days and not unit.startswith(("day", "week")):
            return None, False

        try:
            if unit.startswith("year"):
                return start_date + relativedelta(years=num), False
            elif unit.startswith("month"):
                return start_date + relativedelta(months=num), False
            elif unit.startswith("week"):
                if is_business_days:
                    # Cap the NORMALIZED business-day count: business
                    # weeks multiply the quantity by 5 (issue #44 review).
                    business_days = num * 5
                    if business_days > self._MAX_TERM_QUANTITY:
                        return None, False
                    return self._add_business_days(start_date, business_days), True
                return start_date + timedelta(weeks=num), False
            else:
                if is_business_days:
                    return self._add_business_days(start_date, num), True
                return start_date + timedelta(days=num), False
        except (OverflowError, ValueError):
            # Date arithmetic out of the representable range — fail closed
            # instead of raising (issue #42).
            return None, False

    def _add_business_days(self, start_date: datetime, days: int) -> Optional[datetime]:
        """Add business days to a date, excluding weekends and holidays.

        Returns None when the iteration bound is exceeded — the caller
        fails closed rather than presenting an unbounded-loop result
        (issue #42).
        """
        current = start_date
        added = 0
        # Weekends (~2/7 of days) plus a leap-day/holiday buffer leave
        # ample headroom; hitting the bound means the range is
        # unrepresentable or the calendar pathological.
        max_iterations = days * 2 + 800
        iterations = 0

        while added < days:
            iterations += 1
            if iterations > max_iterations:
                return None
            current += timedelta(days=1)
            # Skip weekends (Saturday=5, Sunday=6)
            if current.weekday() >= 5:
                continue
            # Skip holidays
            if current in self.holiday_calendar:
                continue
            added += 1

        return current
    
    def calculate_business_days_between(
        self,
        start_date: str,
        end_date: str
    ) -> int:
        """
        Calculate the number of business days between two dates.

        Useful for verifying claims like "response required within 10 business days."

        Raises:
            ValueError: If either date is order-ambiguous or partial
                (issues #55, #57) — a silently month-first or
                clock-completed count would be a wrong answer, so the
                caller must disambiguate first.
        """
        ambiguous = [
            label
            for label, raw in (("start_date", start_date), ("end_date", end_date))
            if detect_order_ambiguity(raw)
        ]
        if ambiguous:
            raise ValueError(
                f"Order-ambiguous date(s): {', '.join(ambiguous)}. Supply an "
                f"ISO year-leading date (YYYY-MM-DD) or an unambiguous "
                f"written date."
            )
        incomplete = [
            label
            for label, raw in (("start_date", start_date), ("end_date", end_date))
            if detect_incomplete_date(raw)
        ]
        if incomplete:
            raise ValueError(
                f"Partial date(s): {', '.join(incomplete)}. Supply a "
                f"complete date (YYYY-MM-DD)."
            )
        start = parse_date(start_date)
        end = parse_date(end_date)
        
        if end < start:
            start, end = end, start
        
        count = 0
        current = start
        while current < end:
            current += timedelta(days=1)
            if current.weekday() < 5 and current not in self.holiday_calendar:
                count += 1
        
        return count
