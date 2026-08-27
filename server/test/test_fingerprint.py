from server.lib.ingest import dnb_xlsx, fingerprint


def row(date, desc, amount, source_row=2):
    return dnb_xlsx.RawRow(date, desc, amount, source_row)


def test_fingerprint_is_stable_for_identical_input():
    a = fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -100.0)
    b = fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -100.0)
    assert a == b


def test_fingerprint_differs_on_any_field():
    base = fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -100.0)
    assert base != fingerprint.fingerprint("Kredittkort", "2026-07-01", "Rema", -100.0)
    assert base != fingerprint.fingerprint("Bankkonto", "2026-07-02", "Rema", -100.0)
    assert base != fingerprint.fingerprint("Bankkonto", "2026-07-01", "Meny", -100.0)
    assert base != fingerprint.fingerprint("Bankkonto", "2026-07-01", "Rema", -101.0)


def test_fingerprint_ignores_source_row():
    """Row position must not affect identity, or re-ordered exports duplicate."""
    rows = [row("2026-07-01", "Rema", -100.0, 5),
            row("2026-07-01", "Rema", -100.0, 99)]
    ids = {fp for _, fp, _ in fingerprint.with_identity(rows, "Bankkonto")}
    assert len(ids) == 1


def test_repeat_purchases_get_distinct_occurrence_numbers():
    """Two coffees at one shop on one day are two real transactions."""
    rows = [row("2026-06-30", "PROUD MARY OSLO, Oslo", -238.0, 17),
            row("2026-06-30", "PROUD MARY OSLO, Oslo", -238.0, 19)]
    got = fingerprint.with_identity(rows, "Kredittkort")
    assert [occ for _, _, occ in got] == [1, 2]


def test_distinct_rows_all_get_occurrence_one():
    rows = [row("2026-07-01", "Rema", -100.0),
            row("2026-07-01", "Meny", -100.0)]
    assert [occ for _, _, occ in fingerprint.with_identity(rows, "Bankkonto")] == [1, 1]
