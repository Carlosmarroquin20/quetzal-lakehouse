"""Small invented gold tables, shared by the tests."""

import duckdb
import pytest


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
            ('a11', 'ocds-11', 20261014, 'b-health', 's-acme', 'm-direct', false, '10.00', '1.31'),
            ('a12', 'ocds-12', 20261014, 'b-edu', 's-beta', 'm-direct', false, '5.00', '0.65'),
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
