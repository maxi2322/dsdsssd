from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from . import categorizer, ocr, organizer, parser

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    original_filename: str
    original_path: str
    date: Optional[str]
    amount: Optional[float]
    vat_rate: Optional[float]
    merchant: Optional[str]
    category: Optional[str]
    category_source: Optional[str]
    status: str
    destination: Optional[str]
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def process_file(path: Path, output_dir: Path, config, dry_run: bool, copy: bool) -> ProcessResult:
    """Verarbeitet einen einzelnen Beleg end-to-end: OCR -> Extraktion -> Kategorisierung -> Einsortierung.

    Jeder Fehlerfall (nicht lesbar, keine erkennbaren Felder, Datei kann nicht
    verschoben werden) fuehrt dazu, dass der Beleg in den Ordner zur manuellen
    Pruefung verschoben wird, statt den gesamten Lauf abzubrechen.
    """
    try:
        text, used_ocr = ocr.extract_text(path, config.ocr)
    except Exception as exc:
        logger.warning("OCR fehlgeschlagen fuer %s: %s", path.name, exc)
        return _to_manual_review(path, output_dir, config, dry_run, copy, str(exc))

    try:
        fields = parser.parse_receipt(text)
    except Exception as exc:
        logger.warning("Feldererkennung fehlgeschlagen fuer %s: %s", path.name, exc)
        return _to_manual_review(path, output_dir, config, dry_run, copy, str(exc))

    if fields.amount is None and fields.merchant is None:
        return _to_manual_review(
            path, output_dir, config, dry_run, copy,
            "Weder Betrag noch Haendler erkannt - vermutlich schlechte Bild-/Scanqualitaet",
        )

    try:
        result = categorizer.categorize(fields.merchant, fields.amount, text, config)
    except Exception as exc:
        logger.error("Kategorisierung fehlgeschlagen fuer %s: %s", path.name, exc)
        result = categorizer.CategoryResult(
            category=categorizer.FALLBACK_CATEGORY, source="fallback", note=str(exc)
        )

    destination = organizer.build_destination(output_dir, result.category, fields.date, path.name)
    try:
        final_destination = organizer.place_file(path, destination, dry_run=dry_run, copy=copy)
    except Exception as exc:
        logger.error("Datei konnte nicht einsortiert werden (%s): %s", path.name, exc)
        return _to_manual_review(
            path, output_dir, config, dry_run, copy,
            f"Datei konnte nicht einsortiert werden: {exc}",
        )

    status = "ok"
    note = result.note
    if fields.date is None or fields.amount is None:
        status = "unvollstaendig"
        missing = []
        if fields.date is None:
            missing.append("Datum")
        if fields.amount is None:
            missing.append("Betrag")
        note = (note + "; " if note else "") + f"Nicht erkannt: {', '.join(missing)}"

    return ProcessResult(
        original_filename=path.name,
        original_path=str(path),
        date=fields.date.strftime("%Y-%m-%d") if fields.date else None,
        amount=fields.amount,
        vat_rate=fields.vat_rate,
        merchant=fields.merchant,
        category=result.category,
        category_source=result.source,
        status=status,
        destination=str(final_destination),
        note=note,
    )


def _to_manual_review(path: Path, output_dir: Path, config, dry_run: bool, copy: bool, reason: str) -> ProcessResult:
    manual_dir = output_dir / config.processing.manual_review_dirname
    destination = manual_dir / path.name
    try:
        final_destination = organizer.place_file(path, destination, dry_run=dry_run, copy=copy)
    except Exception as exc:
        logger.error("Konnte Datei nicht in manuelle Pruefung verschieben (%s): %s", path.name, exc)
        final_destination = path

    return ProcessResult(
        original_filename=path.name,
        original_path=str(path),
        date=None,
        amount=None,
        vat_rate=None,
        merchant=None,
        category=None,
        category_source=None,
        status="manuelle_pruefung",
        destination=str(final_destination),
        note=reason,
    )
