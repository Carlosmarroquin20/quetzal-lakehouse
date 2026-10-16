"""The daily digest: a few figures from gold that say what a run produced.

Each function takes a connection whose gold tables are views (see gold.py),
so the same SQL runs against the object store in the job and against small
invented tables in the tests. `build` puts them together into the payload
that is posted to n8n; n8n decides how to word and where to send it.
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import duckdb

KIND = "daily_digest"
# Raised whenever a field is removed or changes meaning, so the receiving
# workflow can refuse a payload it was not written for.
SCHEMA_VERSION = 1

LARGEST_AWARDS = 5

# What a run rebuilds and the digest counts. The dimensions change little
# from one day to the next, so their counts would only make the message longer.
FACT_TABLES = ("fct_exchange_rates", "fct_awards", "fct_budget_execution")


def _number(value: Decimal | None) -> float | None:
    # Gold keeps exact decimals and JSON has a single kind of number. The
    # conversion happens last, after the arithmetic, so no sum or difference
    # carries floating point error.
    return None if value is None else float(value)


def _date_key(day: date) -> int:
    return int(day.strftime("%Y%m%d"))


def exchange_rate(con: duckdb.DuckDBPyConnection, as_of: date) -> dict | None:
    """The latest US dollar rate on or before a day, and how it moved from the day before.

    Gold has a row for every calendar day, so the two latest rows are
    consecutive days. On weekends and on the days the bank does not publish,
    the rate is the last one published and the change is zero.
    """
    rows = con.execute(
        """
        select d.date_day, f.reference_rate, f.is_published, f.rate_published_date
        from fct_exchange_rates as f
        inner join dim_currency as c using (currency_key)
        inner join dim_date as d using (date_key)
        where c.currency_code = 'USD' and f.date_key <= $as_of
        order by f.date_key desc
        limit 2
        """,
        {"as_of": _date_key(as_of)},
    ).fetchall()
    if not rows:
        return None
    day, rate, is_published, published_date = rows[0]
    previous_day, previous_rate = (rows[1][0], rows[1][1]) if len(rows) > 1 else (None, None)
    change = rate - previous_rate if previous_rate is not None else None
    return {
        "currency": "USD",
        "date": day.isoformat(),
        "rate": _number(rate),
        "is_published": is_published,
        "rate_published_date": published_date.isoformat(),
        "previous_date": previous_day.isoformat() if previous_day else None,
        "previous_rate": _number(previous_rate),
        "change": _number(change),
        "change_percent": (
            _number(round(change / previous_rate * 100, 4)) if change is not None else None
        ),
    }


def award_totals(con: duckdb.DuckDBPyConnection, first_day: date, last_day: date) -> dict:
    """Valid awards between two days, both included."""
    count, total_gtq, total_usd = con.execute(
        """
        select
            count(*),
            coalesce(sum(awarded_amount_gtq), 0),
            coalesce(sum(awarded_amount_usd), 0)
        from fct_awards
        where not is_cancelled
            and award_date_key between $first and $last
        """,
        {"first": _date_key(first_day), "last": _date_key(last_day)},
    ).fetchone()
    return {"count": count, "total_gtq": _number(total_gtq), "total_usd": _number(total_usd)}


def masked_supplier_totals(con: duckdb.DuckDBPyConnection, day: date) -> dict:
    """Valid awards of a day to masked suppliers, as a group."""
    count, total_gtq, total_usd = con.execute(
        """
        select
            count(*),
            coalesce(sum(f.awarded_amount_gtq), 0),
            coalesce(sum(f.awarded_amount_usd), 0)
        from fct_awards as f
        inner join dim_supplier as s using (supplier_key)
        where not f.is_cancelled and s.is_masked and f.award_date_key = $day
        """,
        {"day": _date_key(day)},
    ).fetchone()
    return {"count": count, "total_gtq": _number(total_gtq), "total_usd": _number(total_usd)}


def largest_awards(con: duckdb.DuckDBPyConnection, day: date) -> list[dict]:
    """The largest valid awards of a day to legal entities.

    Masked suppliers are left out, as in the dashboard's ranking: the buyer,
    the day and the amount of one award are enough to find its process in
    Guatecompras and read the name gold hides. They are reported as a group
    by masked_supplier_totals.
    """
    rows = con.execute(
        """
        select
            f.ocid,
            s.supplier_name,
            b.buyer_name,
            m.procurement_procedure,
            f.awarded_amount_gtq,
            f.awarded_amount_usd
        from fct_awards as f
        inner join dim_supplier as s using (supplier_key)
        inner join dim_buyer as b using (buyer_key)
        inner join dim_procurement_method as m using (procurement_method_key)
        where not f.is_cancelled and not s.is_masked and f.award_date_key = $day
        order by f.awarded_amount_gtq desc, f.award_id
        limit $limit
        """,
        {"day": _date_key(day), "limit": LARGEST_AWARDS},
    ).fetchall()
    return [
        {
            "ocid": ocid,
            "supplier_name": supplier_name,
            "buyer_name": buyer_name,
            "procurement_procedure": procedure,
            "amount_gtq": _number(amount_gtq),
            "amount_usd": _number(amount_usd),
        }
        for ocid, supplier_name, buyer_name, procedure, amount_gtq, amount_usd in rows
    ]


def row_counts(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    return {
        table: con.execute(f"select count(*) from {table}").fetchone()[0]
        for table in FACT_TABLES
    }


def build(
    con: duckdb.DuckDBPyConnection,
    *,
    run_date: date,
    generated_at: datetime,
    run_id: str | None = None,
) -> dict:
    """The digest of a run made on `run_date`.

    Awards are those of the day before: a run early in the morning has seen
    at most a few hours of the current day.
    """
    award_day = run_date - timedelta(days=1)
    return {
        "kind": KIND,
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "run_date": run_date.isoformat(),
        "generated_at": generated_at.isoformat(),
        "exchange_rate": exchange_rate(con, run_date),
        "awards": {
            "date": award_day.isoformat(),
            **award_totals(con, award_day, award_day),
            "year_to_date": award_totals(con, award_day.replace(month=1, day=1), award_day),
            "masked_suppliers": masked_supplier_totals(con, award_day),
            "largest": largest_awards(con, award_day),
        },
        "row_counts": row_counts(con),
    }
