"""Lokale Web-Oberfläche für die Beleg-Vorsortierung.

Start mit: streamlit run app.py
Öffnet eine Browser-Oberfläche unter http://localhost:8501 - läuft
ausschließlich auf diesem Rechner, Belege werden nicht an einen fremden
Server geschickt (außer für die optionale KI-Kategorisierung: dort wird
Händler/Betrag/Textauszug an die gewählte LLM-API gesendet).
"""

from __future__ import annotations

import json
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import streamlit as st

from receipt_sorter.config import AppConfig
from receipt_sorter.pipeline import process_file
from receipt_sorter.report import build_dataframe, write_excel

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="Beleg-Vorsortierung", page_icon="🧾", layout="wide")

st.title("🧾 Beleg-Vorsortierung für die Steuerberatung")
st.caption(
    "Läuft lokal in deinem Browser auf diesem Rechner. Belege bleiben lokal - "
    "nur bei aktivierter KI-Kategorisierung werden Händler, Betrag und ein "
    "kurzer Textauszug an die gewählte LLM-API gesendet."
)

with st.sidebar:
    st.header("Einstellungen")

    input_mode = st.radio(
        "Belege einlesen über",
        ["Ordnerpfad (für viele Belege)", "Dateien hochladen (Drag & Drop)"],
    )

    input_dir_text = ""
    uploaded_files = None
    if input_mode == "Ordnerpfad (für viele Belege)":
        input_dir_text = st.text_input(
            "Eingabeordner (Pfad auf diesem Rechner)",
            placeholder=r"z.B. C:\Belege oder /home/name/belege",
        )
    else:
        uploaded_files = st.file_uploader(
            "PDF/Bild-Belege hochladen",
            type=["pdf", "jpg", "jpeg", "png", "tif", "tiff", "bmp", "webp"],
            accept_multiple_files=True,
        )

    output_dir_text = st.text_input(
        "Zielordner (sortierte Belege + Excel)",
        placeholder=r"z.B. C:\Belege_sortiert oder /home/name/sortiert",
    )

    config_path_text = st.text_input("Config-Datei (optional)", value="config.yaml")

    st.divider()
    workers = st.slider("Parallele Worker", 1, 16, 4)
    use_llm = st.checkbox("KI-Kategorisierung verwenden", value=True)
    move_files = st.checkbox("Originale verschieben statt kopieren", value=False)
    dry_run = st.checkbox("Nur simulieren (Dry-Run, verändert nichts)", value=False)
    api_key_override = st.text_input(
        "API-Key (optional, überschreibt .env für diesen Lauf)", type="password"
    )

    start = st.button("Belege verarbeiten", type="primary", use_container_width=True)


def _load_config() -> AppConfig | None:
    config_path = Path(config_path_text) if config_path_text.strip() else None
    if config_path is not None and not config_path.exists():
        config_path = None
    try:
        return AppConfig.load(config_path)
    except Exception as exc:
        st.error(f"Konfiguration konnte nicht geladen werden: {exc}")
        return None


def _resolve_input_dir(tmp_dir: tempfile.TemporaryDirectory) -> Path | None:
    if input_mode == "Ordnerpfad (für viele Belege)":
        if not input_dir_text.strip():
            st.error("Bitte einen Eingabeordner angeben.")
            return None
        input_path = Path(input_dir_text)
        if not input_path.is_dir():
            st.error(f"Eingabeordner existiert nicht: {input_path}")
            return None
        return input_path

    if not uploaded_files:
        st.error("Bitte mindestens eine Datei hochladen.")
        return None
    staging_dir = Path(tmp_dir.name)
    for uploaded in uploaded_files:
        (staging_dir / uploaded.name).write_bytes(uploaded.getbuffer())
    return staging_dir


if start:
    if not output_dir_text.strip():
        st.error("Bitte einen Zielordner angeben.")
        st.stop()

    config = _load_config()
    if config is None:
        st.stop()

    config.processing.workers = workers
    config.llm.enabled = use_llm
    if api_key_override.strip():
        os.environ[config.llm.api_key_env] = api_key_override.strip()

    if config.llm.enabled and config.llm.provider != "none" and not config.get_api_key():
        st.warning(
            f"KI-Kategorisierung aktiv, aber {config.llm.api_key_env} ist nicht gesetzt - "
            "es wird nur regelbasiert kategorisiert (Fallback 'Sonstiges')."
        )

    upload_tmp_dir = tempfile.TemporaryDirectory(prefix="beleg_upload_")
    input_path = _resolve_input_dir(upload_tmp_dir)
    if input_path is None:
        upload_tmp_dir.cleanup()
        st.stop()

    output_path = Path(output_dir_text)
    output_path.mkdir(parents=True, exist_ok=True)
    log_dir = output_path / config.processing.log_dirname
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_log_path = log_dir / "verarbeitungsprotokoll.jsonl"
    excel_path = output_path / "Belegübersicht.xlsx"

    extensions = set(config.processing.supported_extensions)
    files = sorted(p for p in input_path.rglob("*") if p.is_file() and p.suffix.lower() in extensions)

    if not files:
        st.warning(f"Keine unterstützten Belege ({', '.join(sorted(extensions))}) gefunden.")
        upload_tmp_dir.cleanup()
        st.stop()

    st.info(f"{len(files)} Belege gefunden. Starte Verarbeitung mit {workers} parallelen Workern ...")
    progress_bar = st.progress(0.0)
    status_text = st.empty()

    all_records = []
    copy_files = not move_files
    ok_count = manual_count = error_count = 0

    with jsonl_log_path.open("a", encoding="utf-8") as log_file, \
         ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(process_file, path, output_path, config, dry_run, copy_files): path
            for path in files
        }
        done = 0
        for future in as_completed(futures):
            path = futures[future]
            try:
                result = future.result()
                record = result.to_dict()
                if record["status"] == "manuelle_pruefung":
                    manual_count += 1
                else:
                    ok_count += 1
            except Exception as exc:
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
            done += 1
            progress_bar.progress(done / len(files))
            status_text.text(
                f"{done}/{len(files)} verarbeitet - ok: {ok_count}, "
                f"zur Prüfung: {manual_count}, Fehler: {error_count}"
            )

    upload_tmp_dir.cleanup()
    write_excel(all_records, excel_path)

    st.success(
        f"Fertig! {ok_count} Belege einsortiert, {manual_count} zur manuellen Prüfung, "
        f"{error_count} Fehler. Ordner: {output_path}"
    )

    df = build_dataframe(all_records)
    st.dataframe(df, use_container_width=True)

    with open(excel_path, "rb") as f:
        st.download_button(
            "📥 Belegübersicht.xlsx herunterladen",
            f,
            file_name="Belegübersicht.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
