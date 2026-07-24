from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

COLUMNS = [
    "Dateiname",
    "Datum",
    "Betrag (EUR)",
    "MwSt-Satz (%)",
    "Haendler",
    "Kategorie",
    "Kategorie-Quelle",
    "Status",
    "Zielpfad",
    "Hinweis",
]


def build_dataframe(records: Iterable[dict]) -> pd.DataFrame:
    rows = []
    for record in records:
        rows.append({
            "Dateiname": record.get("original_filename"),
            "Datum": record.get("date"),
            "Betrag (EUR)": record.get("amount"),
            "MwSt-Satz (%)": record.get("vat_rate"),
            "Haendler": record.get("merchant"),
            "Kategorie": record.get("category"),
            "Kategorie-Quelle": record.get("category_source"),
            "Status": record.get("status"),
            "Zielpfad": record.get("destination"),
            "Hinweis": record.get("note"),
        })
    df = pd.DataFrame(rows, columns=COLUMNS)
    if not df.empty:
        df = df.sort_values(by=["Kategorie", "Datum"], na_position="last")
    return df


def write_excel(records: Iterable[dict], output_path: Path) -> None:
    df = build_dataframe(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        sheet_name = "Belegübersicht"
        df.to_excel(writer, index=False, sheet_name=sheet_name)
        worksheet = writer.sheets[sheet_name]
        for idx, column in enumerate(df.columns, start=1):
            values = [column] + [str(v) for v in df[column].astype(str).tolist()]
            max_len = max(len(v) for v in values)
            column_letter = worksheet.cell(row=1, column=idx).column_letter
            worksheet.column_dimensions[column_letter].width = min(max_len + 2, 60)
