"""Shared connection and cached query results for the Streamlit pages."""

from collections.abc import Callable

import duckdb
import pandas as pd
import streamlit as st

from quetzal_dashboard import gold, queries

# Gold is rebuilt once a day, so an hour-old answer is fresh enough and saves
# reading the files again on every click.
RESULTS_TTL = "1h"


@st.cache_resource(show_spinner=False)
def _connection() -> duckdb.DuckDBPyConnection:
    return gold.connect()


def load(query: Callable[..., pd.DataFrame | list], *args: object) -> pd.DataFrame | list:
    """Run one of the functions of queries.py, caching its result."""
    # Streamlit cannot use a function as a cache key, so results are cached
    # by the function's name.
    return _load(query.__name__, *args)


@st.cache_data(ttl=RESULTS_TTL, show_spinner="Reading gold...")
def _load(query_name: str, *args: object) -> pd.DataFrame | list:
    # Each call gets its own cursor: the connection is shared by every viewer
    # of the app, and a DuckDB connection must not run two queries at once.
    return getattr(queries, query_name)(_connection().cursor(), *args)
