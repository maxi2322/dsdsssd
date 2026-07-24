from datetime import datetime

from receipt_sorter.parser import parse_receipt


def test_parse_date_amount_vat_merchant():
    text = """
    Bäckerei Mustermann
    Musterstrasse 1, 12345 Musterstadt
    Datum: 03.04.2024
    Kaffee 1x 2,50
    MwSt 19% enthalten
    Gesamt 12,90 EUR
    """
    fields = parse_receipt(text)
    assert fields.date == datetime(2024, 4, 3)
    assert fields.amount == 12.90
    assert fields.vat_rate == 19.0
    assert "Bäckerei Mustermann" in fields.merchant


def test_parse_two_digit_year():
    text = "Datum: 05.06.23\nGesamt 5,00 EUR"
    fields = parse_receipt(text)
    assert fields.date == datetime(2023, 6, 5)


def test_parse_amount_prefers_labeled_total_over_line_items():
    text = "Kaffee 2,50\nKuchen 3,00\nGesamt 5,50 EUR"
    fields = parse_receipt(text)
    assert fields.amount == 5.50


def test_parse_receipt_without_recognizable_fields():
    fields = parse_receipt("unleserlicher text ohne jegliche struktur oder zahlen")
    assert fields.date is None
    assert fields.amount is None
    assert fields.vat_rate is None
