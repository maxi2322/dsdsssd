# Beleg-Vorsortierung für die Steuerberatung

Lokale Python-Anwendung, die einen Ordner mit bis zu ~8000 Belegen (PDF oder
Bild) automatisiert vorbereitet:

1. **OCR** (Tesseract, lokal) liest Datum, Betrag, MwSt-Satz und Händlername aus.
2. Ein **Sprachmodell** (Anthropic- oder OpenAI-API) ordnet jeden Beleg anhand
   von Händler, Betrag und Kontext einer deutschen Buchhaltungskategorie zu
   (Reisekosten, Bewirtung, Büromaterial, Fahrzeugkosten, Miete, Sonstiges, …).
   Bekannte Händler werden vorab kostenlos per Stichwortregel zugeordnet, das
   Sprachmodell wird nur für den Rest befragt.
3. Jeder Beleg wird in `<Kategorie>/<Jahr-Monat>/` einsortiert.
4. Eine **Excel-Übersicht** (`Belegübersicht.xlsx`) mit Datum, Betrag,
   MwSt-Satz, Händler, Kategorie und Dateiname wird erzeugt – fertig für die
   Übergabe an den Steuerberater.
5. Belege, die nicht gelesen/erkannt werden können, landen in
   `_Manuelle_Pruefung/` statt den Lauf abzubrechen.
6. Ein Fortschrittsbalken zeigt den Verarbeitungsstand bei großen Mengen.

## Installation

### Systemvoraussetzungen

- Python 3.10+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) inkl. deutschem
  Sprachpaket (`tesseract-ocr-deu`)
- [Poppler](https://poppler.freedesktop.org/) (für `pdftoppm`, wird zum
  Rendern gescannter PDF-Seiten benötigt)

```bash
# Debian/Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-deu poppler-utils

# macOS (Homebrew)
brew install tesseract tesseract-lang poppler
```

Unter Windows: Tesseract- und Poppler-Installer herunterladen und den Pfad in
`config.yaml` unter `ocr.tesseract_cmd` bzw. im `PATH` hinterlegen.

### Python-Abhängigkeiten

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### API-Key für die Kategorisierung

```bash
cp .env.example .env
# .env editieren und ANTHROPIC_API_KEY (oder OPENAI_API_KEY) eintragen
```

Ohne API-Key funktioniert die Anwendung weiterhin – es wird dann nur
regelbasiert kategorisiert, unbekannte Händler landen in "Sonstiges".

### Konfiguration

```bash
cp config.example.yaml config.yaml
```

Passe darin Kategorien, Stichwortregeln, LLM-Anbieter/Modell und die Anzahl
paralleler Worker an.

## Nutzung

```bash
python -m receipt_sorter --input ./belege --output ./sortiert --config config.yaml
```

Wichtige Optionen:

| Option        | Bedeutung |
|---------------|-----------|
| `--dry-run`   | Nur simulieren, es werden keine Dateien kopiert/verschoben und keine Excel-Datei final geschrieben (Protokoll wird trotzdem erzeugt) |
| `--move`      | Originaldateien verschieben statt kopieren (Standard: Originale bleiben unangetastet) |
| `--no-llm`    | Nur regelbasiert kategorisieren, keine API-Aufrufe |
| `--workers N` | Anzahl paralleler Verarbeitungen (Default aus config.yaml, sonst 4) |
| `--log-level` | z. B. `DEBUG` für ausführlichere Ausgabe |

Beispiel für einen ersten Testlauf ohne Risiko:

```bash
python -m receipt_sorter --input ./belege --output ./sortiert-test --dry-run --log-level DEBUG
```

## Ergebnis

```
sortiert/
├── Bewirtung/
│   └── 2024-04/
│       └── beleg_restaurant_001.pdf
├── Fahrzeugkosten/
│   └── 2024-05/
│       └── tankstelle_003.jpg
├── _Manuelle_Pruefung/
│   └── unleserlicher_scan.pdf
├── _Verarbeitungsprotokoll/
│   └── verarbeitungsprotokoll.jsonl
└── Belegübersicht.xlsx
```

Das JSONL-Protokoll wird bei jedem Lauf ergänzt und dient sowohl als
Fehlerprotokoll als auch als Grundlage für die Excel-Datei – wird die
Verarbeitung unterbrochen (z. B. bei 8000 Belegen), kann sie einfach erneut
gestartet werden: bereits einsortierte Dateien liegen nicht mehr im
Eingabeordner und werden nicht doppelt verarbeitet.

## Architektur

| Modul | Aufgabe |
|-------|---------|
| `receipt_sorter/ocr.py` | Text aus PDF (eingebetteter Text oder OCR-Fallback) bzw. Bild extrahieren |
| `receipt_sorter/parser.py` | Datum, Betrag, MwSt-Satz, Händlername per Regex/Heuristik aus dem Text ziehen |
| `receipt_sorter/categorizer.py` | Regelbasierte Kategorisierung, optional per LLM (Anthropic/OpenAI) |
| `receipt_sorter/organizer.py` | Zielpfad bilden, Datei kopieren/verschieben, Namenskollisionen auflösen |
| `receipt_sorter/report.py` | Excel-Übersicht erzeugen |
| `receipt_sorter/pipeline.py` | Verarbeitung eines einzelnen Belegs inkl. Fehlerbehandlung |
| `receipt_sorter/cli.py` | Kommandozeile, Threadpool, Fortschrittsanzeige, Protokollierung |

## Hinweise & Grenzen

- Die Feldererkennung basiert auf Heuristiken (typische deutsche
  Belegformate). Bei ungewöhnlichen Layouts können Felder fehlen – diese
  Belege werden als „unvollständig“ markiert bzw. bei komplettem Fehlschlag
  in die manuelle Prüfung verschoben. Die Excel-Übersicht sollte vor der
  Übergabe an den Steuerberater kurz gegenprüft werden.
- Bei 8000 Belegen und aktivierter KI-Kategorisierung fallen entsprechend
  viele API-Aufrufe an – Kosten und Rate-Limits des gewählten Anbieters
  beachten. `--no-llm` bzw. gezielte Stichwortregeln reduzieren die Anzahl
  der Aufrufe.
- Standardmäßig werden Originaldateien **kopiert**, nicht verschoben, damit
  bei Fehlern nichts verloren geht. `--move` verschiebt sie stattdessen.

## Tests

```bash
pytest
```

Die Tests decken Feldererkennung, Kategorisierungslogik, Dateiorganisation
und Excel-Export ab (ohne echte OCR-/API-Aufrufe).
