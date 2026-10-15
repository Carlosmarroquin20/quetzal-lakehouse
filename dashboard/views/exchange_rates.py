"""The quetzal to US dollar exchange rate, from fct_exchange_rates."""

from datetime import timedelta

import streamlit as st

from quetzal_dashboard import queries
from quetzal_dashboard.cache import load
from quetzal_dashboard.charts import rate_line

st.title("Exchange rate")
st.caption(
    "Quetzales per US dollar, as published by the Banco de Guatemala. The "
    "reference rate is the midpoint of the buying and selling rates. Days the "
    "bank did not publish carry the last rate published before them."
)

rates = load(queries.daily_rates)
if rates.empty:
    st.warning("Gold has no exchange rates yet. Run the pipeline first.")
    st.stop()

first_day = rates["date_day"].min().date()
last_day = rates["date_day"].max().date()
start, end = st.slider(
    "Days shown",
    min_value=first_day,
    max_value=last_day,
    # The last five years by default; the whole history goes back to 1989.
    value=(max(first_day, last_day - timedelta(days=5 * 365)), last_day),
    format="YYYY-MM-DD",
)
shown = rates[rates["date_day"].dt.date.between(start, end)]

latest = rates.iloc[-1]
latest_kpi, lowest_kpi, highest_kpi = st.columns(3)
latest_kpi.metric(
    f"Latest rate ({latest['date_day']:%Y-%m-%d})", f"{latest['reference_rate']:.5f}"
)
lowest_kpi.metric("Lowest in the days shown", f"{shown['reference_rate'].min():.5f}")
highest_kpi.metric("Highest in the days shown", f"{shown['reference_rate'].max():.5f}")

st.altair_chart(rate_line(shown), width="stretch")

st.subheader("Per year")
st.dataframe(
    load(queries.yearly_rates),
    hide_index=True,
    column_config={
        "year": st.column_config.NumberColumn("Year", format="%d"),
        "days": "Days",
        "filled_days": "Days not published",
        "average_rate": st.column_config.NumberColumn("Average", format="%.5f"),
        "lowest_rate": st.column_config.NumberColumn("Lowest", format="%.5f"),
        "highest_rate": st.column_config.NumberColumn("Highest", format="%.5f"),
    },
)
