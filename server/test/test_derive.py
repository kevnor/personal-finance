from server.lib import derive

LOAN = ("Lån  422687 Lån 1516.09.18257 "
        "Avdrag Kr 3.407,26Renter Kr 9.816,49")


def test_splits_into_interest_principal_and_fee():
    rows = derive.split_loan_term(LOAN, -13288.75)
    assert {r.category for r in rows} == {
        "Mortgage - interest", "Mortgage - principal", "Mortgage - fees"}


def test_parts_sum_back_to_the_original_charge():
    rows = derive.split_loan_term(LOAN, -13288.75)
    assert round(sum(r.amount for r in rows), 2) == -13288.75


def test_interest_and_principal_parsed_from_norwegian_number_format():
    by_cat = {r.category: r.amount
              for r in derive.split_loan_term(LOAN, -13288.75)}
    assert by_cat["Mortgage - interest"] == -9816.49
    assert by_cat["Mortgage - principal"] == -3407.26
    assert by_cat["Mortgage - fees"] == -65.0


def test_no_fee_row_when_parts_account_for_the_whole_charge():
    rows = derive.split_loan_term(LOAN, -13223.75)
    assert {r.category for r in rows} == {
        "Mortgage - interest", "Mortgage - principal"}


def test_returns_empty_for_a_non_loan_description():
    assert derive.split_loan_term("Varekjøp Rema Lorenveien", -161.14) == []


def test_returns_empty_when_only_one_component_present():
    assert derive.split_loan_term("Lån 123 Avdrag Kr 100,00", -100.0) == []


def test_derived_amounts_keep_the_sign_of_the_source():
    rows = derive.split_loan_term(LOAN, -13288.75)
    assert all(r.amount < 0 for r in rows)
