from __future__ import annotations

import argparse
import json
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tqdm import tqdm

from .config import AppConfig
from .pipeline import process_file
from .report import write_excel

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

logger = logging.getLogger("receipt_sorter")


def _iter_receipt_files(input_dir: Path, extensions: set):
    for path in sorted(input_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in extensions:
            yield path


def _load_existing_log(log_path: Path) -> list:
    records = []
    if log_path.exists():
        with log_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Ungueltige Zeile im Protokoll ignoriert: %s", line[:80])
    return records


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="receipt_sorter",
        description=(
            "Sortiert Belege (PDF/Bild) automatisiert per OCR und KI-Kategorisierung "
            "nach Kategorie und Monat vor und erstellt eine Excel-Uebersicht fuer den Steuerberater."
        ),
    )
    ap.add_argument("--input", required=True, type=Path, help="Ordner mit den Original-Belegen")
    ap.add_argument("--output", required=True, type=Path, help="Zielordner fuer die sortierten Belege")
    ap.add_argument("--config", type=Path, default=None, help="Pfad zu einer config.yaml")
    ap.add_argument("--workers", type=int, default=None, help="Anzahl paralleler Verarbeitungen (Default: aus Config, sonst 4)")
    ap.add_argument("--dry-run", action="store_true", help="Nur simulieren - keine Dateien kopieren/verschieben")
    ap.add_argument("--move", action="store_true", help="Originaldateien verschieben statt kopieren (Standard: kopieren)")
    ap.add_argument("--no-llm", action="store_true", help="KI-Kategorisierung deaktivieren, nur Stichwort-Regeln verwenden")
    ap.add_argument("--log-level", default="INFO", help="Logging-Level, z.B. DEBUG, INFO, WARNING")
    return ap


def main(argv=None) -> int:
    args = build_arg_parser().parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    input_dir: Path = args.input
    output_dir: Path = args.output

    if not input_dir.is_dir():
        logger.error("Eingabeordner existiert nicht oder ist kein Verzeichnis: %s", input_dir)
        return 1

    try:
        config = AppConfig.load(args.config)
    except Exception as exc:
        logger.error("Konfiguration konnte nicht geladen werden: %s", exc)
        return 1

    if args.workers:
        config.processing.workers = args.workers
    if args.no_llm:
        config.llm.enabled = False

    if config.llm.enabled and config.llm.provider != "none" and not config.get_api_key():
        logger.warning(
            "KI-Kategorisierung ist aktiviert, aber die Umgebungsvariable %s ist nicht gesetzt. "
            "Es wird ausschliesslich regelbasiert kategorisiert (Fallback 'Sonstiges').",
            config.llm.api_key_env,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    log_dir = output_dir / config.processing.log_dirname
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_log_path = log_dir / "verarbeitungsprotokoll.jsonl"
    excel_path = output_dir / "Belegübersicht.xlsx"

    extensions = set(config.processing.supported_extensions)
    files = list(_iter_receipt_files(input_dir, extensions))

    if not files:
        logger.warning("Keine unterstuetzten Belege (%s) in %s gefunden.", ", ".join(sorted(extensions)), input_dir)
        return 0

    logger.info(
        "Gefunden: %d Belege. Starte Verarbeitung mit %d parallelen Workern (%s).",
        len(files), config.processing.workers, "kopieren" if not args.move else "verschieben",
    )

    all_records = _load_existing_log(jsonl_log_path)
    copy_files = not args.move

    ok_count = 0
    manual_review_count = 0
    error_count = 0

    with jsonl_log_path.open("a", encoding="utf-8") as log_file, \
         ThreadPoolExecutor(max_workers=max(1, config.processing.workers)) as executor:

        futures = {
            executor.submit(process_file, path, output_dir, config, args.dry_run, copy_files): path
            for path in files
        }

        progress = tqdm(as_completed(futures), total=len(futures), desc="Belege werden verarbeitet", unit="Beleg")
        for future in progress:
            path = futures[future]
            try:
                result = future.result()
                record = result.to_dict()
                if record["status"] == "manuelle_pruefung":
                    manual_review_count += 1
                else:
                    ok_count += 1
            except Exception as exc:
                logger.error("Unerwarteter Fehler bei %s: %s", path.name, exc)
                error_count += 1
                record = {
                    "original_filename": path.name,
                    "original_path": str(path),
                    "date": None,
                    "amount": None,
                    "vat_rate": None,
                    "merchant": None,
                    "category": None,
                    "category_source": None,
                    "status": "fehler",
                    "destination": None,
                    "note": str(exc),
                }

            all_records.append(record)
            log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            log_file.flush()
            progress.set_postfix(ok=ok_count, pruefen=manual_review_count, fehler=error_count)

    write_excel(all_records, excel_path)

    logger.info(
        "Fertig. %d Belege erfolgreich einsortiert, %d zur manuellen Pruefung, %d Fehler. "
        "Excel-Uebersicht: %s",
        ok_count, manual_review_count, error_count, excel_path,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
