"""Deterministic, rule-based matching of incoming payments to capital calls.

Scoring (out of 100):
  * capital call reference found in the description (e.g. "CC-1001", "cc1001")  +40
  * investor name found in the description                                       +40
  * amount exactly equals the call's available balance                           +20

A match is *suggested* when the score reaches SUGGEST_THRESHOLD and no review
flag was raised. Anything else is sent to manual review, keeping the best
candidate (if any) so the reviewer can still approve it with one click.

Review flags (always force manual review):
  * reference and investor name point to different investors
  * reference not found for this organization
  * amount larger than the call's available balance
  * several open calls for the investor and the amount does not single one out
  * payment dated before the capital call was issued
"""

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .csv_parser import normalize_text
from .models import CapitalCall, Investor

SUGGEST_THRESHOLD = 60
REFERENCE_SCORE = 40
NAME_SCORE = 40
EXACT_AMOUNT_SCORE = 20

CALL_REFERENCE_RE = re.compile(r"\bCC[\s_-]?(\d{3,})\b", re.IGNORECASE)
LEGAL_SUFFIXES = {"LLC", "INC", "LP", "LLP", "LTD", "CORP", "CO", "PLC", "LIMITED"}


@dataclass
class MatchResult:
    investor: Investor | None = None
    capital_call: CapitalCall | None = None
    confidence: int = 0
    reasons: list[str] = field(default_factory=list)
    review_reasons: list[str] = field(default_factory=list)

    @property
    def is_confident(self):
        return self.capital_call is not None and not self.review_reasons and self.confidence >= SUGGEST_THRESHOLD


def extract_call_reference(*texts: str) -> str | None:
    for text in texts:
        found = CALL_REFERENCE_RE.search(text or "")
        if found:
            return f"CC-{found.group(1)}"
    return None


def investor_match_key(name: str) -> str:
    """Normalised investor name without trailing legal suffixes ("Haller Capital LLC" -> "HALLER CAPITAL")."""
    tokens = normalize_text(name).split()
    while len(tokens) > 1 and tokens[-1] in LEGAL_SUFFIXES:
        tokens.pop()
    return " ".join(tokens)


def find_investor_by_name(description: str, investors) -> tuple[Investor | None, bool]:
    """Return (investor, ambiguous). The longest matching name wins; equal-length ties are ambiguous."""
    haystack = f" {normalize_text(description)} "
    hits = []
    for investor in investors:
        key = investor_match_key(investor.name)
        if key and f" {key} " in haystack:
            hits.append((len(key), investor))
    if not hits:
        return None, False
    hits.sort(key=lambda hit: hit[0], reverse=True)
    if len(hits) > 1 and hits[0][0] == hits[1][0] and hits[0][1] != hits[1][1]:
        return None, True
    return hits[0][1], False


class Matcher:
    """Matches transactions for a single organization.

    ``reserved`` tracks amounts already earmarked for each capital call by other
    unreviewed suggestions, so two payments in the same statement cannot both be
    suggested against the same remaining balance.
    """

    def __init__(self, organization, reserved: dict[int, Decimal] | None = None):
        self.organization = organization
        self.investors = list(Investor.objects.filter(organization=organization))
        self.calls = list(
            CapitalCall.objects.filter(organization=organization).select_related("investor").order_by("call_date", "id")
        )
        self.calls_by_reference = {call.reference.upper(): call for call in self.calls}
        self.reserved = dict(reserved or {})

    def available_balance(self, call: CapitalCall) -> Decimal:
        return call.remaining_amount - self.reserved.get(call.id, Decimal("0"))

    def reserve(self, result: MatchResult, amount: Decimal):
        if result.capital_call is not None:
            call_id = result.capital_call.id
            self.reserved[call_id] = self.reserved.get(call_id, Decimal("0")) + amount

    def match(self, description: str, bank_reference: str, amount: Decimal, transaction_date) -> MatchResult:
        result = MatchResult()
        call_ref = extract_call_reference(description, bank_reference)
        name_investor, name_ambiguous = find_investor_by_name(description, self.investors)

        if name_ambiguous:
            result.review_reasons.append("Description matches more than one investor name.")

        call = None
        if call_ref:
            call = self.calls_by_reference.get(call_ref)
            if call is None:
                result.review_reasons.append(f"Capital call reference {call_ref} was not found for this organization.")
            else:
                result.confidence += REFERENCE_SCORE
                result.reasons.append(f"Capital call reference {call.reference} found in description.")
                if name_investor is not None:
                    if name_investor.id == call.investor_id:
                        result.confidence += NAME_SCORE
                        result.reasons.append(f"Investor name '{name_investor.name}' matches the capital call.")
                    else:
                        result.review_reasons.append(
                            f"Name '{name_investor.name}' conflicts with {call.reference}, "
                            f"which belongs to '{call.investor.name}'."
                        )

        if call is None and name_investor is not None:
            result.investor = name_investor
            result.confidence += NAME_SCORE
            result.reasons.append(f"Investor name '{name_investor.name}' found in description.")
            call = self._pick_open_call_for(name_investor, amount, result)

        if call is None and name_investor is None and not call_ref and not name_ambiguous:
            result.review_reasons.append("No capital call reference or known investor name found.")

        if call is not None:
            result.capital_call = call
            result.investor = call.investor
            self._check_amount_and_date(call, amount, transaction_date, result)
            if not result.review_reasons and result.confidence < SUGGEST_THRESHOLD:
                result.review_reasons.append(
                    f"Low confidence ({result.confidence}/100): needs a capital call reference "
                    f"or an amount equal to the outstanding balance."
                )

        return result

    def _pick_open_call_for(self, investor, amount, result) -> CapitalCall | None:
        open_calls = [
            call for call in self.calls
            if call.investor_id == investor.id and self.available_balance(call) > 0
        ]
        if not open_calls:
            result.review_reasons.append(f"'{investor.name}' has no capital call with an outstanding balance.")
            return None
        if len(open_calls) == 1:
            return open_calls[0]
        exact = [call for call in open_calls if self.available_balance(call) == amount]
        if len(exact) == 1:
            result.reasons.append(f"Amount singles out {exact[0].reference} among the investor's open calls.")
            return exact[0]
        result.review_reasons.append(
            f"'{investor.name}' has {len(open_calls)} open capital calls; choose the correct one."
        )
        return None

    def _check_amount_and_date(self, call, amount, transaction_date, result):
        available = self.available_balance(call)
        if amount == available:
            result.confidence += EXACT_AMOUNT_SCORE
            result.reasons.append(f"Amount equals the outstanding balance of {call.reference}.")
        elif amount < available:
            result.reasons.append(f"Partial payment: {amount:,.2f} of {available:,.2f} outstanding.")
        else:
            reserved = self.reserved.get(call.id, Decimal("0"))
            detail = f" ({reserved:,.2f} is already earmarked by other unreviewed payments)" if reserved else ""
            result.review_reasons.append(
                f"Amount {amount:,.2f} exceeds the available balance of {available:,.2f} on {call.reference}{detail}."
            )
        if transaction_date < call.call_date:
            result.review_reasons.append(
                f"Payment date {transaction_date} is before {call.reference} was issued on {call.call_date}."
            )
