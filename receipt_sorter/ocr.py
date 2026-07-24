from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple

from PIL import Image

logger = logging.getLogger(__name__)


class OCRError(Exception):
    """Wird ausgelöst, wenn aus einem Beleg kein Text gewonnen werden kann."""


def _configure_tesseract(tesseract_cmd) -> None:
    import pytesseract

    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def extract_text(path: Path, ocr_config) -> Tuple[str, bool]:
    """Extrahiert den Text eines Belegs. Gibt (Text, wurde_OCR_verwendet) zurück."""
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _extract_from_pdf(path, ocr_config)
    return _extract_from_image(path, ocr_config), True


def _extract_from_pdf(path: Path, ocr_config) -> Tuple[str, bool]:
    import pdfplumber

    text_parts = []
    try:
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                text_parts.append(page.extract_text() or "")
    except Exception as exc:
        logger.debug("pdfplumber konnte %s nicht direkt lesen: %s", path.name, exc)

    embedded_text = "\n".join(text_parts).strip()
    if len(embedded_text) >= ocr_config.min_embedded_text_length:
        # Textbasiertes PDF (z. B. digitale Rechnung) - keine OCR nötig.
        return embedded_text, False

    # Vermutlich gescanntes PDF ohne eingebetteten Text -> OCR über die Seitenbilder.
    ocr_text = _ocr_pdf(path, ocr_config)
    combined = (embedded_text + "\n" + ocr_text).strip()
    if not combined:
        raise OCRError(f"Kein Text im PDF gefunden: {path.name}")
    return combined, True


def _ocr_pdf(path: Path, ocr_config) -> str:
    from pdf2image import convert_from_path
    import pytesseract

    _configure_tesseract(ocr_config.tesseract_cmd)

    try:
        images = convert_from_path(
            str(path), dpi=ocr_config.dpi, poppler_path=ocr_config.poppler_path
        )
    except Exception as exc:
        raise OCRError(
            f"PDF konnte nicht in Bilder umgewandelt werden ({path.name}): {exc}. "
            "Ist Poppler (pdftoppm) installiert bzw. ocr.poppler_path korrekt gesetzt?"
        ) from exc

    pages_text = []
    for image in images:
        pages_text.append(pytesseract.image_to_string(image, lang=ocr_config.lang))
    return "\n".join(pages_text)


def _extract_from_image(path: Path, ocr_config) -> str:
    import pytesseract

    _configure_tesseract(ocr_config.tesseract_cmd)

    try:
        with Image.open(path) as img:
            grayscale = img.convert("L")
            text = pytesseract.image_to_string(grayscale, lang=ocr_config.lang)
    except OCRError:
        raise
    except Exception as exc:
        raise OCRError(f"Bild konnte nicht verarbeitet werden ({path.name}): {exc}") from exc

    if not text.strip():
        raise OCRError(f"OCR ergab keinen lesbaren Text: {path.name}")
    return text
