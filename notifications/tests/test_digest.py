"""The daily digest, computed from small invented gold tables."""

import json
from datetime import UTC, date, datetime

import duckdb
import pytest

from quetzal_notifications import digest

RUN_DATE = date(2026, 10, 15)
AWARD_DAY = date(2026, 10, 14)


@pytest.fixture
def con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(
        """
        create table dim_date as
        select strftime(d, '%Y%m%d')::integer as date_key, d::date as date_day
        from range(date '2025-12-01', date '2026-10-31', interval 1 day) as t(d);

        create table dim_currency as
        select * from (values ('c-usd', 'USD'), ('c-gtq', 'GTQ'))
            as t(currency_key, currency_code);

        -- 2026-10-15 was not published and repeats the rate of the 14th. The
        -- 16th is after the run and must not be reported.
        create table fct_exchange_rates as
        select
            date_key, currency_key, reference_rate::decimal(11, 7) as reference_rate,
            is_published, rate_published_date::date as rate_published_date
        from (values
            (20261012, 'c-usd', '7.6300000', true, '2026-10-12'),
            (20261013, 'c-usd', '7.6338100', true, '2026-10-13'),
            (20261014, 'c-usd', '7.6400000', true, '2026-10-14'),
            (20261015, 'c-usd', '7.6400000', false, '2026-10-14'),
            (20261016, 'c-usd', '7.7000000', true, '2026-10-16'),
            (20261015, 'c-gtq', '1.0000000', true, '2026-10-15')
        ) as t(date_key, currency_key, reference_rate, is_published, rate_published_date);

        create table dim_supplier as
        select * from (values
            ('s-acme', 'ACME, S.A.', false),
            ('s-beta', 'BETA, S.A.', false),
            ('s-person', 'Natural person', true),
            ('s-unknown', 'Supplier of unknown legal type', true)
        ) as t(supplier_key, supplier_name, is_masked);

        create table dim_buyer as
        select * from (values ('b-health', 'MINISTERIO DE SALUD'), ('b-edu', 'MINISTERIO DE EDUCACION'))
            as t(buyer_key, buyer_name);

        create table dim_procurement_method as
        select * from (values ('m-direct', 'Compra directa'), ('m-tender', 'Licitación pública'))
            as t(procurement_method_key, procurement_procedure);

        create table fct_awards as
        select
            award_id, ocid, award_date_key, buyer_key, supplier_key, procurement_method_key,
            is_cancelled,
            awarded_amount_gtq::decimal(18, 2) as awarded_amount_gtq,
            awarded_amount_usd::decimal(18, 2) as awarded_amount_usd
        from (values
            ('a1', 'ocds-1', 20261014, 'b-health', 's-acme', 'm-tender', false, '700.00', '91.62'),
            ('a2', 'ocds-2', 20261014, 'b-edu', 's-person', 'm-direct', false, '900.00', '117.80'),
            ('a3', 'ocds-3', 20261014, 'b-edu', 's-unknown', 'm-direct', false, '50.00', '6.54'),
            ('a4', 'ocds-4', 20261014, 'b-health', 's-beta', 'm-direct', false, '40.00', '5.24'),
            ('a5', 'ocds-5', 20261014, 'b-health', 's-beta', 'm-direct', false, '30.00', '3.93'),
            ('a6', 'ocds-6', 20261014, 'b-edu', 's-acme', 'm-direct', false, '20.00', '2.62'),
            -- Cancelled: larger than any other award, and never counted.
            ('a7', 'ocds-7', 20261014, 'b-edu', 's-beta', 'm-tender', true, '99999.00', '13088.87'),
            -- Earlier in the year, and in the previous year.
            ('a8', 'ocds-8', 20260105, 'b-edu', 's-beta', 'm-direct', false, '100.00', '13.05'),
            ('a9', 'ocds-9', 20251231, 'b-edu', 's-beta', 'm-direct', false, '5000.00', '652.00'),
            -- The day of the run, which is not over yet.
            ('a10', 'ocds-10', 20261015, 'b-edu', 's-beta', 'm-direct', false, '8.00', '1.05')
        ) as t(
            award_id, ocid, award_date_key, buyer_key, supplier_key, procurement_method_key,
            is_cancelled, awarded_amount_gtq, awarded_amount_usd
        );

        create table fct_budget_execution as
        select * from range(3) as t(budget_line);
        """
    )
    return con


def test_the_rate_is_compared_with_the_day_before(con):
    rate = digest.exchange_rate(con, AWARD_DAY)

    assert rate == {
        "currency": "USD",
        "date": "2026-10-14",
        "rate": 7.64,
        "is_published": True,
        "rate_published_date": "2026-10-14",
        "previous_date": "2026-10-13",
        "previous_rate": 7.63381,
        "change": 0.00619,
        "change_percent": 0.0811,
    }


def test_a_day_without_a_published_rate_repeats_the_last_one(con):
    rate = digest.exchange_rate(con, RUN_DATE)

    assert rate["date"] == "2026-10-15"
    assert rate["is_published"] is False
    assert rate["rate_published_date"] == "2026-10-14"
    assert rate["change"] == 0
    assert rate["change_percent"] == 0


def test_rates_after_the_run_date_are_ignored(con):
    assert digest.exchange_rate(con, RUN_DATE)["rate"] == 7.64


def test_no_rate_on_or_before_the_day(con):
    assert digest.exchange_rate(con, date(2026, 1, 1)) is None


def test_award_totals_count_valid_awards_only(con):
    assert digest.award_totals(con, AWARD_DAY, AWARD_DAY) == {
        "count": 6,
        "total_gtq": 1740.0,
        "total_usd": 227.75,
    }


def test_year_to_date_starts_on_the_first_of_january(con):
    totals = digest.award_totals(con, date(2026, 1, 1), AWARD_DAY)

    assert totals["count"] == 7
    assert totals["total_gtq"] == 1840.0


def test_largest_awards_come_first_and_are_limited(con):
    largest = digest.largest_awards(con, AWARD_DAY)

    assert len(largest) == digest.LARGEST_AWARDS
    assert [award["amount_gtq"] for award in largest] == [900.0, 700.0, 50.0, 40.0, 30.0]
    assert largest[1] == {
        "ocid": "ocds-1",
        "supplier_name": "ACME, S.A.",
        "supplier_is_masked": False,
        "buyer_name": "MINISTERIO DE SALUD",
        "procurement_procedure": "Licitación pública",
        "amount_gtq": 700.0,
        "amount_usd": 91.62,
    }


def test_masked_suppliers_cannot_be_traced_through_their_process(con):
    masked = [a for a in digest.largest_awards(con, AWARD_DAY) if a["supplier_is_masked"]]

    assert [a["supplier_name"] for a in masked] == [
        "Natural person",
        "Supplier of unknown legal type",
    ]
    assert all(a["ocid"] is None for a in masked)


def test_a_day_without_awards(con):
    day = date(2026, 10, 1)

    assert digest.award_totals(con, day, day) == {"count": 0, "total_gtq": 0, "total_usd": 0}
    assert digest.largest_awards(con, day) == []


def test_row_counts_of_the_fact_tables(con):
    assert digest.row_counts(con) == {
        "fct_exchange_rates": 6,
        "fct_awards": 10,
        "fct_budget_execution": 3,
    }


def test_the_payload_has_the_agreed_shape(con):
    generated_at = datetime(2026, 10, 15, 12, 30, tzinfo=UTC)

    payload = digest.build(con, run_date=RUN_DATE, generated_at=generated_at, run_id="run-1")

    assert set(payload) == {
        "kind", "schema_version", "run_id", "run_date", "generated_at",
        "exchange_rate", "awards", "row_counts",
    }
    assert payload["kind"] == "daily_digest"
    assert payload["schema_version"] == 1
    assert payload["run_id"] == "run-1"
    assert payload["run_date"] == "2026-10-15"
    assert payload["generated_at"] == "2026-10-15T12:30:00+00:00"
    assert set(payload["exchange_rate"]) == {
        "currency", "date", "rate", "is_published", "rate_published_date",
        "previous_date", "previous_rate", "change", "change_percent",
    }
    assert set(payload["awards"]) == {
        "date", "count", "total_gtq", "total_usd", "year_to_date", "largest",
    }
    assert payload["awards"]["date"] == "2026-10-14"
    assert set(payload["awards"]["year_to_date"]) == {"count", "total_gtq", "total_usd"}
    assert set(payload["row_counts"]) == set(digest.FACT_TABLES)


def test_the_payload_survives_a_round_trip_through_json(con):
    payload = digest.build(con, run_date=RUN_DATE, generated_at=datetime.now(UTC))

    assert json.loads(json.dumps(payload)) == payload


def test_the_payload_of_an_empty_day(con):
    payload = digest.build(con, run_date=date(2026, 10, 2), generated_at=datetime.now(UTC))

    assert payload["run_id"] is None
    assert payload["awards"]["count"] == 0
    assert payload["awards"]["largest"] == []
