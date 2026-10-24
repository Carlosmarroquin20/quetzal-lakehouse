"""The gold tables the tests invent are held to gold's contract."""

import duckdb
import pytest

from gold_contract import conform_to_contract, gold_contract
from quetzal_dashboard.gold import TABLES


def test_every_table_read_is_a_gold_model():
    assert set(TABLES) <= set(gold_contract())


def test_a_column_gold_does_not_have_is_refused():
    con = duckdb.connect()
    con.execute("create table dim_currency as select 'USD' as currency_code, '$' as currency_symbol")

    with pytest.raises(ValueError, match="currency_symbol in dim_currency"):
        conform_to_contract(con)


def test_a_table_takes_the_types_of_the_contract():
    con = duckdb.connect()
    con.execute("create table fct_exchange_rates as select 20261014 as date_key, 7.64 as reference_rate")

    conform_to_contract(con)

    types = dict(
        con.execute(
            "select column_name, data_type from duckdb_columns() where table_name = 'fct_exchange_rates'"
        ).fetchall()
    )
    assert types["reference_rate"] == "DECIMAL(11,7)"
    assert list(types) == list(gold_contract()["fct_exchange_rates"])
