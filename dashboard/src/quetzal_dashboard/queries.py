"""The questions the dashboard asks gold.

Each function takes a connection whose gold tables are views (see gold.py) and
returns a DataFrame, so the same SQL runs against the object store in the app
and against small invented tables in the tests.
"""

import duckdb
import pandas as pd


def award_years(con: duckdb.DuckDBPyConnection) -> list[int]:
    """Years with at least one award, most recent first."""
    rows = con.execute(
        """
        select distinct d.year
        from fct_awards as f
        inner join dim_date as d on d.date_key = f.award_date_key
        order by d.year desc
        """
    ).fetchall()
    return [year for (year,) in rows]


def award_totals(con: duckdb.DuckDBPyConnection, year: int) -> pd.DataFrame:
    """Valid awards of a year, how many were cancelled, and the last day with awards."""
    return con.execute(
        """
        select
            count(*) filter (where not f.is_cancelled) as awards,
            coalesce(sum(f.awarded_amount_gtq) filter (where not f.is_cancelled), 0) as amount_gtq,
            coalesce(sum(f.awarded_amount_usd) filter (where not f.is_cancelled), 0) as amount_usd,
            count(*) filter (where f.is_cancelled) as cancelled_awards,
            max(d.date_day) as last_award_date
        from fct_awards as f
        inner join dim_date as d on d.date_key = f.award_date_key
        where d.year = $year
        """,
        {"year": year},
    ).df()


def awards_per_month(con: duckdb.DuckDBPyConnection, year: int) -> pd.DataFrame:
    """Valid awards of a year by month of award."""
    return con.execute(
        """
        select
            d.first_day_of_month as month,
            count(*) as awards,
            sum(f.awarded_amount_gtq) as amount_gtq,
            sum(f.awarded_amount_usd) as amount_usd
        from fct_awards as f
        inner join dim_date as d on d.date_key = f.award_date_key
        where d.year = $year and not f.is_cancelled
        group by d.first_day_of_month
        order by month
        """,
        {"year": year},
    ).df()


def awards_by_procedure(con: duckdb.DuckDBPyConnection, year: int) -> pd.DataFrame:
    """Valid awards of a year by procurement procedure, largest amount first."""
    return con.execute(
        """
        select
            m.procurement_procedure,
            count(*) as awards,
            sum(f.awarded_amount_gtq) as amount_gtq,
            sum(f.awarded_amount_usd) as amount_usd
        from fct_awards as f
        inner join dim_date as d on d.date_key = f.award_date_key
        inner join dim_procurement_method as m using (procurement_method_key)
        where d.year = $year and not f.is_cancelled
        group by m.procurement_procedure
        order by amount_gtq desc
        """,
        {"year": year},
    ).df()


def top_named_suppliers(
    con: duckdb.DuckDBPyConnection, year: int, limit: int = 10
) -> pd.DataFrame:
    """The suppliers awarded the most in a year, among those gold names.

    Masked suppliers (natural persons, and those whose legal type is unknown)
    are left out: gold does not name them, and ranking them one by one would
    single out individuals by their amounts.
    """
    return con.execute(
        """
        select
            s.supplier_name,
            s.supplier_id,
            count(*) as awards,
            sum(f.awarded_amount_gtq) as amount_gtq,
            sum(f.awarded_amount_usd) as amount_usd
        from fct_awards as f
        inner join dim_date as d on d.date_key = f.award_date_key
        inner join dim_supplier as s using (supplier_key)
        where d.year = $year and not f.is_cancelled and not s.is_masked
        group by s.supplier_key, s.supplier_name, s.supplier_id
        order by amount_gtq desc, s.supplier_name
        limit $limit
        """,
        {"year": year, "limit": limit},
    ).df()


def awards_by_supplier_kind(con: duckdb.DuckDBPyConnection, year: int) -> pd.DataFrame:
    """Valid awards of a year to named suppliers and, as a group, to masked ones."""
    return con.execute(
        """
        select
            case when s.is_masked then s.supplier_name else 'Legal entity' end as supplier_kind,
            count(distinct s.supplier_key) as suppliers,
            count(*) as awards,
            sum(f.awarded_amount_gtq) as amount_gtq,
            sum(f.awarded_amount_usd) as amount_usd
        from fct_awards as f
        inner join dim_date as d on d.date_key = f.award_date_key
        inner join dim_supplier as s using (supplier_key)
        where d.year = $year and not f.is_cancelled
        group by supplier_kind
        order by amount_gtq desc
        """,
        {"year": year},
    ).df()
