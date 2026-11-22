from extractors.type1_reader import (
    RawRow,
    read_type1_rows,
    write_type1_rows,
)


def test_type1_rows_round_trip_through_text_file(tmp_path):
    rows = [
        RawRow(entry="0800", exit="1600", total="8.00"),
        RawRow(entry="", exit="", total=""),
    ]
    path = tmp_path / "nested" / "type1_rows.txt"

    assert write_type1_rows(rows, path) == path
    assert read_type1_rows(path) == rows


def test_type1_rows_reject_invalid_text_file_format(tmp_path):
    path = tmp_path / "invalid.txt"
    path.write_text("entry\texit\n0800\t1600\n", encoding="utf-8")

    try:
        read_type1_rows(path)
    except ValueError as exc:
        assert "Invalid type1 OCR text file format" in str(exc)
    else:
        raise AssertionError("Invalid OCR text format should raise ValueError")
