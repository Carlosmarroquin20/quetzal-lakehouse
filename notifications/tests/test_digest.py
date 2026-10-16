"""The daily digest, computed from small invented gold tables."""

import json
from datetime import UTC, date, datetime

from quetzal_notifications import digest

RUN_DATE = date(2026, 10, 15)
AWARD_DAY = date(2026, 10, 14)


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
        "count": 8,
        "total_gtq": 1755.0,
        "total_usd": 229.71,
    }


def test_year_to_date_starts_on_the_first_of_january(con):
    totals = digest.award_totals(con, date(2026, 1, 1), AWARD_DAY)

    assert totals["count"] == 9
    assert totals["total_gtq"] == 1855.0


def test_largest_awards_come_first_and_are_limited(con):
    largest = digest.largest_awards(con, AWARD_DAY)

    assert len(largest) == digest.LARGEST_AWARDS
    assert [award["amount_gtq"] for award in largest] == [700.0, 40.0, 30.0, 20.0, 10.0]
    assert largest[0] == {
        "ocid": "ocds-1",
        "supplier_name": "ACME, S.A.",
        "buyer_name": "MINISTERIO DE SALUD",
        "procurement_procedure": "Licitación pública",
        "amount_gtq": 700.0,
        "amount_usd": 91.62,
    }


def test_masked_suppliers_are_not_ranked_one_by_one(con):
    largest = digest.largest_awards(con, AWARD_DAY)

    assert {award["supplier_name"] for award in largest} == {"ACME, S.A.", "BETA, S.A."}
    assert "ocds-2" not in {award["ocid"] for award in largest}


def test_masked_suppliers_are_reported_as_a_group(con):
    assert digest.masked_supplier_totals(con, AWARD_DAY) == {
        "count": 2,
        "total_gtq": 950.0,
        "total_usd": 124.34,
    }


def test_a_day_without_awards(con):
    day = date(2026, 10, 1)

    assert digest.award_totals(con, day, day) == {"count": 0, "total_gtq": 0, "total_usd": 0}
    assert digest.largest_awards(con, day) == []
    assert digest.masked_supplier_totals(con, day)["count"] == 0


def test_row_counts_of_the_fact_tables(con):
    assert digest.row_counts(con) == {
        "fct_exchange_rates": 6,
        "fct_awards": 12,
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
        "date", "count", "total_gtq", "total_usd", "year_to_date", "masked_suppliers",
        "largest",
    }
    assert payload["awards"]["date"] == "2026-10-14"
    assert set(payload["awards"]["year_to_date"]) == {"count", "total_gtq", "total_usd"}
    assert set(payload["awards"]["masked_suppliers"]) == {"count", "total_gtq", "total_usd"}
    assert set(payload["awards"]["largest"][0]) == {
        "ocid", "supplier_name", "buyer_name", "procurement_procedure", "amount_gtq", "amount_usd",
    }
    assert set(payload["row_counts"]) == set(digest.FACT_TABLES)


def test_the_payload_survives_a_round_trip_through_json(con):
    payload = digest.build(con, run_date=RUN_DATE, generated_at=datetime.now(UTC))

    assert json.loads(json.dumps(payload)) == payload


def test_the_payload_of_an_empty_day(con):
    payload = digest.build(con, run_date=date(2026, 10, 2), generated_at=datetime.now(UTC))

    assert payload["run_id"] is None
    assert payload["awards"]["count"] == 0
    assert payload["awards"]["largest"] == []
