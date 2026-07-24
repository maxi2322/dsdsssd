from datetime import datetime
from pathlib import Path

from receipt_sorter.organizer import build_destination, place_file, unique_path


def test_build_destination_with_date():
    dest = build_destination(Path("/out"), "Bewirtung", datetime(2024, 4, 3), "beleg.pdf")
    assert dest == Path("/out/Bewirtung/2024-04/beleg.pdf")


def test_build_destination_without_date():
    dest = build_destination(Path("/out"), "Sonstiges", None, "beleg.pdf")
    assert dest == Path("/out/Sonstiges/Unbekanntes_Datum/beleg.pdf")


def test_build_destination_sanitizes_category():
    dest = build_destination(Path("/out"), "Fahrzeug/Kosten", None, "beleg.pdf")
    assert "/" not in dest.parent.parent.name


def test_unique_path_appends_counter(tmp_path):
    existing = tmp_path / "beleg.pdf"
    existing.write_text("x")
    result = unique_path(existing)
    assert result == tmp_path / "beleg_1.pdf"


def test_place_file_copy_keeps_original(tmp_path):
    source = tmp_path / "quelle.pdf"
    source.write_text("inhalt")
    destination = tmp_path / "ziel" / "quelle.pdf"

    result = place_file(source, destination, dry_run=False, copy=True)

    assert source.exists()
    assert result.exists()
    assert result.read_text() == "inhalt"


def test_place_file_move_removes_original(tmp_path):
    source = tmp_path / "quelle.pdf"
    source.write_text("inhalt")
    destination = tmp_path / "ziel" / "quelle.pdf"

    result = place_file(source, destination, dry_run=False, copy=False)

    assert not source.exists()
    assert result.exists()


def test_place_file_dry_run_does_nothing(tmp_path):
    source = tmp_path / "quelle.pdf"
    source.write_text("inhalt")
    destination = tmp_path / "ziel" / "quelle.pdf"

    result = place_file(source, destination, dry_run=True, copy=True)

    assert source.exists()
    assert not result.exists()
