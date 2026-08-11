#!/usr/bin/env python3
"""Parse and audit al-Isabah biography-entry sequences."""
from __future__ import annotations

import re
from collections import Counter


DIGIT_MAP = str.maketrans(
    "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
    "\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9",
    "01234567890123456789",
)
ENTRY_RE = re.compile(
    r"(?m)^\s*[\[(]?\s*(\d{5})\s*[\])]?\s*(?:[-\u2013\u2014.:]|\))"
)
VOLUME8_FIRST_ENTRY = 10759
VOLUME8_LAST_ENTRY = 12308


def normalize_digits(value: str) -> str:
    return value.translate(DIGIT_MAP)


def probable_entry_numbers(text: str) -> list[int]:
    return [int(value) for value in ENTRY_RE.findall(normalize_digits(text))]


def audit_entry_sequence(
    numbers: list[int],
    *,
    expected_first: int,
    expected_last: int,
) -> dict:
    if expected_last < expected_first:
        raise ValueError("expected_last must be greater than or equal to expected_first")
    expected = list(range(expected_first, expected_last + 1))
    counts = Counter(numbers)
    gaps = [number for number in expected if counts[number] == 0]
    duplicates = [
        {"entry_number": number, "count": count}
        for number, count in sorted(counts.items())
        if count > 1
    ]
    out_of_range = sorted(
        number
        for number in counts
        if number < expected_first or number > expected_last
    )
    reversals = [
        {"previous": left, "next": right}
        for left, right in zip(numbers, numbers[1:])
        if right < left
    ]
    return {
        "expected_first": expected_first,
        "expected_last": expected_last,
        "expected_count": len(expected),
        "observed_count": len(numbers),
        "observed_first": numbers[0] if numbers else None,
        "observed_last": numbers[-1] if numbers else None,
        "gap_count": len(gaps),
        "gaps": gaps,
        "duplicate_count": len(duplicates),
        "duplicates": duplicates,
        "reversal_count": len(reversals),
        "reversals": reversals,
        "out_of_range_count": len(out_of_range),
        "out_of_range": out_of_range,
        "pass": numbers == expected,
    }
