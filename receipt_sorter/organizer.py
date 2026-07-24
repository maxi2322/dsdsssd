from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

INVALID_PATH_CHARS = '<>:"/\\|?*'


def _sanitize(name: str) -> str:
    cleaned = "".join(c for c in name if c not in INVALID_PATH_CHARS).strip()
    return cleaned or "Unbekannt"


def build_destination(output_dir: Path, category: str, date, filename: str) -> Path:
    category_dir = _sanitize(category)
    month_dir = date.strftime("%Y-%m") if date is not None else "Unbekanntes_Datum"
    return output_dir / category_dir / month_dir / filename


def unique_path(path: Path) -> Path:
    """Haengt bei Namenskollisionen einen Zaehler an, statt Dateien zu ueberschreiben."""
    if not path.exists():
        return path
    stem, suffix, parent = path.stem, path.suffix, path.parent
    counter = 1
    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def place_file(source: Path, destination: Path, dry_run: bool = False, copy: bool = True) -> Path:
    """Kopiert (Standard) oder verschiebt eine Datei an ihren Zielort."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination = unique_path(destination)
    if not dry_run:
        if copy:
            shutil.copy2(source, destination)
        else:
            shutil.move(str(source), str(destination))
    return destination
