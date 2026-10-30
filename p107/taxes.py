"""Flat-rate capital-gain netting with character-preserving carryforwards.

Same-character netting precedes cross-character netting. No ordinary-income
loss deduction, carryback, brackets, or wash-sale adjudication is implemented.
"""
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class TaxResult:
    tax: float
    taxable_st: float
    taxable_lt: float
    carry_st: float
    carry_lt: float
    loss_used_st: float
    loss_used_lt: float


def settle(gain_st, gain_lt, loss_st, loss_lt, carry_st, carry_lt, rate_st, rate_lt):
    vals = (gain_st, gain_lt, loss_st, loss_lt, carry_st, carry_lt, rate_st, rate_lt)
    if any(not isfinite(v) or v < 0 for v in vals):
        raise ValueError('Tax amounts and rates must be finite and nonnegative')
    if rate_st >= 1 or rate_lt >= 1:
        raise ValueError('Tax rates must be below 1')
    s, l = gain_st - loss_st - carry_st, gain_lt - loss_lt - carry_lt
    if s < 0 < l:
        offset = min(-s, l)
        s, l = s + offset, l - offset
    elif l < 0 < s:
        offset = min(-l, s)
        l, s = l + offset, s - offset
    cs, cl = max(-s, 0.0), max(-l, 0.0)
    return TaxResult(max(s, 0) * rate_st + max(l, 0) * rate_lt,
                     max(s, 0), max(l, 0), cs, cl,
                     loss_st + carry_st - cs, loss_lt + carry_lt - cl)
