from pathlib import Path

from receipt_sorter.report import build_dataframe, write_excel


def test_build_dataframe_maps_fields():
    records = [
        {
            "original_filename": "beleg.pdf",
            "date": "2024-04-03",
            "amount": 12.9,
            "vat_rate": 19.0,
            "merchant": "Baeckerei Mustermann",
            "category": "Bewirtung",
            "category_source": "regel",
            "status": "ok",
            "destination": "/out/Bewirtung/2024-04/beleg.pdf",
            "note": "",
        }
    ]
    df = build_dataframe(records)
    assert list(df["Dateiname"]) == ["beleg.pdf"]
    assert list(df["Kategorie"]) == ["Bewirtung"]


def test_write_excel_creates_file(tmp_path):
    records = [
        {
            "original_filename": "beleg.pdf",
            "date": "2024-04-03",
            "amount": 12.9,
            "vat_rate": 19.0,
            "merchant": "Baeckerei Mustermann",
            "category": "Bewirtung",
            "category_source": "regel",
            "status": "ok",
            "destination": "/out/Bewirtung/2024-04/beleg.pdf",
            "note": "",
        }
    ]
    output_path = tmp_path / "Belegübersicht.xlsx"
    write_excel(records, output_path)
    assert output_path.exists()


def test_write_excel_handles_empty_records(tmp_path):
    output_path = tmp_path / "leer.xlsx"
    write_excel([], output_path)
    assert output_path.exists()
