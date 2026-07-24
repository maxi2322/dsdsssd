from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

DATE_PATTERNS = [
    re.compile(r"\b(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{4})\b"),
    re.compile(r"\b(\d{1,2})[.\/-](\d{1,2})[.\/-](\d{2})\b"),
]
DATE_KEYWORDS = ("datum", "rechnungsdatum", "belegdatum", "beleg vom", "ausstellungsdatum")

AMOUNT_KEYWORDS = (
    "gesamt", "summe", "total", "endbetrag", "zu zahlen",
    "gesamtbetrag", "rechnungsbetrag", "zwischensumme",
)
AMOUNT_PATTERN = re.compile(r"(\d{1,3}(?:[.\s]\d{3})*,\d{2})\s*(?:€|eur)?")

VAT_PATTERN = re.compile(r"(\d{1,2}(?:[,.]\d{1,2})?)\s?%")
VAT_CONTEXT_KEYWORDS = ("mwst", "ust", "mehrwertsteuer", "umsatzsteuer", "vat")

HEADER_STOPWORDS = (
    "rechnung", "beleg", "kassenbon", "quittung", "bon", "invoice",
    "receipt", "datum", "uhrzeit", "kunde", "steuernummer", "ust-id",
)


@dataclass
class ReceiptFields:
    date: Optional[datetime]
    amount: Optional[float]
    vat_rate: Optional[float]
    merchant: Optional[str]
    raw_text: str


def _to_float(value: str) -> float:
    normalized = value.replace(".", "").replace(" ", "").replace(",", ".")
    return float(normalized)


def _parse_date(lines: List[str]) -> Optional[datetime]:
    candidates = []
    for line in lines:
        lower = line.lower()
        for pattern in DATE_PATTERNS:
            for match in pattern.finditer(line):
                day, month, year = match.groups()
                year_int = int(year)
                if year_int < 100:
                    year_int += 2000
                try:
                    dt = datetime(year_int, int(month), int(day))
                except ValueError:
                    continue
                priority = 1 if any(kw in lower for kw in DATE_KEYWORDS) else 0
                candidates.append((priority, dt))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def _parse_amount(lines: List[str]) -> Optional[float]:
    labeled = []
    all_amounts = []
    for line in lines:
        lower = line.lower()
        for match in AMOUNT_PATTERN.finditer(line):
            try:
                value = _to_float(match.group(1))
            except ValueError:
                continue
            all_amounts.append(value)
            if any(kw in lower for kw in AMOUNT_KEYWORDS):
                labeled.append(value)
    if labeled:
        return max(labeled)
    if all_amounts:
        return max(all_amounts)
    return None


def _parse_vat(lines: List[str]) -> Optional[float]:
    candidates = []
    for line in lines:
        lower = line.lower()
        for match in VAT_PATTERN.finditer(line):
            try:
                value = float(match.group(1).replace(",", "."))
            except ValueError:
                continue
            if value > 100:
                continue
            priority = 1 if any(kw in lower for kw in VAT_CONTEXT_KEYWORDS) else 0
            candidates.append((priority, value))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def _parse_merchant(lines: List[str]) -> Optional[str]:
    for line in lines[:10]:
        stripped = line.strip()
        if len(stripped) < 3:
            continue
        lower = stripped.lower()
        if any(word in lower for word in HEADER_STOPWORDS):
            continue
        if sum(ch.isalpha() for ch in stripped) < 3:
            continue
        if re.fullmatch(r"[\d.,\-\s€%]+", stripped):
            continue
        return stripped
    return None


def parse_receipt(text: str) -> ReceiptFields:
    lines = [line for line in text.splitlines() if line.strip()]
    return ReceiptFields(
        date=_parse_date(lines),
        amount=_parse_amount(lines),
        vat_rate=_parse_vat(lines),
        merchant=_parse_merchant(lines),
        raw_text=text,
    )
