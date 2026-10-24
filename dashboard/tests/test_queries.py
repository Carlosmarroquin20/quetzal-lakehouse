"""The dashboard's queries, run against small invented gold tables."""

import duckdb
import pandas as pd
import pytest

from quetzal_dashboard import queries

from gold_contract import conform_to_contract


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        """
        create table dim_date as
        select * from (values
            (20250115, date '2025-01-15', 2025, date '2025-01-01'),
            (20250220, date '2025-02-20', 2025, date '2025-02-01'),
            (20260310, date '2026-03-10', 2026, date '2026-03-01')
        ) as t(date_key, date_day, year, first_day_of_month);

        create table dim_procurement_method as
        select * from (values
            ('m-direct', 'Compra directa'),
            ('m-tender', 'Licitación pública')
        ) as t(procurement_method_key, procurement_procedure);

        -- Two legal entities, two natural persons and one supplier of unknown
        -- legal type, already masked the way dim_supplier masks them.
        create table dim_supplier as
        select * from (values
            ('s-acme', '1234567', 'ACME, S.A.', false),
            ('s-beta', '7654321', 'BETA, S.A.', false),
            ('s-person-1', null, 'Natural person', true),
            ('s-person-2', null, 'Natural person', true),
            ('s-unknown', null, 'Supplier of unknown legal type', true)
        ) as t(supplier_key, supplier_id, supplier_name, is_masked);

        create table fct_awards as
        select * from (values
            (20250115, 'm-tender', 's-acme', 'b-health', false, 700.0, 90.0),
            (20250115, 'm-direct', 's-beta', 'b-health', false, 100.0, 13.0),
            (20250220, 'm-direct', 's-person-1', 'b-edu', false, 50.0, 6.5),
            (20250220, 'm-direct', 's-person-2', 'b-edu', false, 30.0, 3.9),
            (20250220, 'm-direct', 's-unknown', 'b-edu', false, 20.0, 2.6),
            (20250220, 'm-tender', 's-beta', 'b-edu', true, 999.0, 130.0),
            (20260310, 'm-direct', 's-acme', 'b-health', false, 5.0, 0.7)
        ) as t(
            award_date_key, procurement_method_key, supplier_key, buyer_key,
            is_cancelled, awarded_amount_gtq, awarded_amount_usd
        );

        create table dim_entity as
        select * from (values
            ('e-health', 'MINISTERIO DE SALUD'),
            ('e-edu', 'MINISTERIO DE EDUCACIÓN'),
            ('e-debt', 'SERVICIOS DE LA DEUDA PÚBLICA'),
            ('e-muni', 'MUNICIPALIDAD')
        ) as t(entity_key, entity_name);

        -- A municipality buys but has no budget lines: it is not part of the
        -- central government budget.
        create table dim_buyer as
        select * from (values
            ('b-health', 'e-health'),
            ('b-edu', 'e-edu'),
            ('b-muni', 'e-muni')
        ) as t(buyer_key, entity_key);

        create table fct_budget_execution as
        select * from (values
            (2025, 'e-health', 600.0, 400.0, 350.0),
            (2025, 'e-health', 400.0, 200.0, 150.0),
            (2025, 'e-edu', 2000.0, 1500.0, 1400.0),
            (2025, 'e-debt', 3000.0, 2900.0, 2900.0),
            (2026, 'e-health', 1100.0, 300.0, 200.0)
        ) as t(fiscal_year, entity_key, current_budget, accrued, paid);

        create table dim_currency as
        select * from (values ('c-gtq', 'GTQ'), ('c-usd', 'USD'))
        as t(currency_key, currency_code);

        -- The second day was not published and carries the rate of the day
        -- before. The quetzal row checks that only dollar rates are read.
        create table fct_exchange_rates as
        select * from (values
            (20250115, 'c-usd', 7.70, 7.69, 7.71, true, date '2025-01-15'),
            (20250220, 'c-usd', 7.72, 7.71, 7.73, false, date '2025-02-19'),
            (20260310, 'c-usd', 7.64, 7.63, 7.65, true, date '2026-03-10'),
            (20260310, 'c-gtq', 1.00, 1.00, 1.00, true, date '2026-03-10')
        ) as t(
            date_key, currency_key, reference_rate, buy_rate, sell_rate,
            is_published, rate_published_date
        );
        """
    )
    conform_to_contract(con)
    return con


def test_award_years_are_listed_most_recent_first(con):
    assert queries.award_years(con) == [2026, 2025]


def test_totals_leave_out_cancelled_awards_but_count_them(con):
    totals = queries.award_totals(con, 2025).iloc[0]

    assert totals["awards"] == 5
    assert totals["amount_gtq"] == pytest.approx(900.0)
    assert totals["amount_usd"] == pytest.approx(116.0)
    assert totals["cancelled_awards"] == 1
    assert str(totals["last_award_date"].date()) == "2025-02-20"


def test_totals_of_a_year_without_awards_are_zero(con):
    totals = queries.award_totals(con, 2024).iloc[0]

    assert totals["awards"] == 0
    assert totals["amount_gtq"] == 0


def test_awards_are_grouped_by_month_of_award(con):
    per_month = queries.awards_per_month(con, 2025)

    assert per_month["awards"].tolist() == [2, 3]
    assert per_month["amount_gtq"].tolist() == pytest.approx([800.0, 100.0])


def test_procedures_are_ordered_by_amount(con):
    by_procedure = queries.awards_by_procedure(con, 2025)

    assert by_procedure["procurement_procedure"].tolist() == [
        "Licitación pública",
        "Compra directa",
    ]
    assert by_procedure["amount_gtq"].tolist() == pytest.approx([700.0, 200.0])


def test_top_suppliers_never_include_masked_ones(con):
    top = queries.top_named_suppliers(con, 2025)

    assert top["supplier_name"].tolist() == ["ACME, S.A.", "BETA, S.A."]
    assert top["supplier_id"].notna().all()


def test_top_suppliers_respect_the_limit(con):
    assert len(queries.top_named_suppliers(con, 2025, limit=1)) == 1


def test_masked_suppliers_only_appear_as_groups(con):
    by_kind = queries.awards_by_supplier_kind(con, 2025).set_index("supplier_kind")

    assert by_kind.loc["Legal entity", "suppliers"] == 2
    assert by_kind.loc["Natural person", "suppliers"] == 2
    assert by_kind.loc["Natural person", "amount_gtq"] == pytest.approx(80.0)
    assert by_kind.loc["Supplier of unknown legal type", "awards"] == 1


def test_daily_rates_are_dollar_rates_in_date_order(con):
    rates = queries.daily_rates(con)

    assert rates["reference_rate"].tolist() == pytest.approx([7.70, 7.72, 7.64])
    assert rates["is_published"].tolist() == [True, False, True]


def test_yearly_rates_count_the_filled_days(con):
    yearly = queries.yearly_rates(con).set_index("year")

    assert yearly.index.tolist() == [2026, 2025]
    assert yearly.loc[2025, "days"] == 2
    assert yearly.loc[2025, "filled_days"] == 1
    assert yearly.loc[2025, "average_rate"] == pytest.approx(7.71)
    assert yearly.loc[2025, "highest_rate"] == pytest.approx(7.72)


def test_budget_years_are_listed_most_recent_first(con):
    assert queries.budget_years(con) == [2026, 2025]


def test_budget_lines_add_up_per_entity(con):
    budget = queries.budget_by_entity(con, 2025).set_index("entity_name")

    assert budget.index.tolist() == [
        "SERVICIOS DE LA DEUDA PÚBLICA",
        "MINISTERIO DE EDUCACIÓN",
        "MINISTERIO DE SALUD",
    ]
    assert budget.loc["MINISTERIO DE SALUD", "current_budget"] == pytest.approx(1000.0)
    assert budget.loc["MINISTERIO DE SALUD", "execution_rate"] == pytest.approx(0.6)


def test_valid_awards_reach_the_entity_of_their_buyer(con):
    budget = queries.budget_by_entity(con, 2025).set_index("entity_name")

    assert budget.loc["MINISTERIO DE SALUD", "awarded"] == pytest.approx(800.0)
    # The cancelled award of 999 is left out.
    assert budget.loc["MINISTERIO DE EDUCACIÓN", "awarded"] == pytest.approx(100.0)
    assert pd.isna(budget.loc["SERVICIOS DE LA DEUDA PÚBLICA", "awarded"])
