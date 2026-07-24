from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_CATEGORIES = [
    "Reisekosten",
    "Bewirtung",
    "Büromaterial",
    "Fahrzeugkosten",
    "Miete",
    "Telekommunikation",
    "Versicherung",
    "Marketing und Werbung",
    "Fortbildung",
    "Sonstiges",
]

# Schnelle, kostenlose Vorab-Kategorisierung per Stichwort im Händlernamen.
# Nur wenn keine Regel greift, wird (falls aktiviert) das Sprachmodell befragt.
DEFAULT_RULES = {
    "tankstelle": "Fahrzeugkosten",
    "shell": "Fahrzeugkosten",
    "aral": "Fahrzeugkosten",
    "esso": "Fahrzeugkosten",
    "totalenergies": "Fahrzeugkosten",
    "total energies": "Fahrzeugkosten",
    "jet tankstelle": "Fahrzeugkosten",
    "restaurant": "Bewirtung",
    "café": "Bewirtung",
    "cafe": "Bewirtung",
    "bäckerei": "Bewirtung",
    "gastst": "Bewirtung",
    "bahn": "Reisekosten",
    "db fernverkehr": "Reisekosten",
    "db vertrieb": "Reisekosten",
    "lufthansa": "Reisekosten",
    "hotel": "Reisekosten",
    "flixbus": "Reisekosten",
    "staples": "Büromaterial",
    "mcpaper": "Büromaterial",
    "büro": "Büromaterial",
    "buerobedarf": "Büromaterial",
    "telekom": "Telekommunikation",
    "vodafone": "Telekommunikation",
    "o2": "Telekommunikation",
    "1&1": "Telekommunikation",
    "versicherung": "Versicherung",
    "hausverwaltung": "Miete",
    "miete": "Miete",
}

SUPPORTED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class LLMConfig:
    provider: str = "anthropic"  # "anthropic" | "openai" | "none"
    model: str = "claude-haiku-4-5-20251001"
    api_key_env: str = "ANTHROPIC_API_KEY"
    max_retries: int = 3
    timeout_seconds: int = 30
    enabled: bool = True


@dataclass
class OCRConfig:
    tesseract_cmd: Optional[str] = None
    lang: str = "deu+eng"
    dpi: int = 300
    min_embedded_text_length: int = 20


@dataclass
class ProcessingConfig:
    workers: int = 4
    supported_extensions: tuple = tuple(sorted(SUPPORTED_EXTENSIONS))
    manual_review_dirname: str = "_Manuelle_Pruefung"
    log_dirname: str = "_Verarbeitungsprotokoll"


@dataclass
class AppConfig:
    categories: list = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    rules: dict = field(default_factory=lambda: dict(DEFAULT_RULES))
    llm: LLMConfig = field(default_factory=LLMConfig)
    ocr: OCRConfig = field(default_factory=OCRConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)

    @classmethod
    def load(cls, path: Optional[Path]) -> "AppConfig":
        cfg = cls()
        if path is None:
            return cfg
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Konfigurationsdatei nicht gefunden: {path}")
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if data.get("categories"):
            cfg.categories = list(data["categories"])
        if data.get("rules"):
            cfg.rules = {str(k).lower(): v for k, v in data["rules"].items()}

        llm_data = data.get("llm") or {}
        cfg.llm = LLMConfig(
            provider=llm_data.get("provider", cfg.llm.provider),
            model=llm_data.get("model", cfg.llm.model),
            api_key_env=llm_data.get("api_key_env", cfg.llm.api_key_env),
            max_retries=int(llm_data.get("max_retries", cfg.llm.max_retries)),
            timeout_seconds=int(llm_data.get("timeout_seconds", cfg.llm.timeout_seconds)),
            enabled=bool(llm_data.get("enabled", cfg.llm.enabled)),
        )

        ocr_data = data.get("ocr") or {}
        cfg.ocr = OCRConfig(
            tesseract_cmd=ocr_data.get("tesseract_cmd", cfg.ocr.tesseract_cmd),
            lang=ocr_data.get("lang", cfg.ocr.lang),
            dpi=int(ocr_data.get("dpi", cfg.ocr.dpi)),
            min_embedded_text_length=int(
                ocr_data.get("min_embedded_text_length", cfg.ocr.min_embedded_text_length)
            ),
        )

        proc_data = data.get("processing") or {}
        exts = proc_data.get("supported_extensions")
        cfg.processing = ProcessingConfig(
            workers=int(proc_data.get("workers", cfg.processing.workers)),
            supported_extensions=tuple(exts) if exts else cfg.processing.supported_extensions,
            manual_review_dirname=proc_data.get(
                "manual_review_dirname", cfg.processing.manual_review_dirname
            ),
            log_dirname=proc_data.get("log_dirname", cfg.processing.log_dirname),
        )
        return cfg

    def get_api_key(self) -> Optional[str]:
        return os.environ.get(self.llm.api_key_env)
