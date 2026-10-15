"""Budget execution of the central government, from fct_budget_execution."""

import streamlit as st

from quetzal_dashboard import queries
from quetzal_dashboard.cache import load
from quetzal_dashboard.charts import execution_bars, in_millions, millions

AMOUNTS = ["current_budget", "accrued", "paid", "awarded"]

st.title("Budget execution")
st.caption(
    "Expenditure budget of the central government entities, from the yearly "
    "workbooks of the Ministerio de Finanzas Públicas. A closed year shows the "
    "whole year; the current one accumulates up to the day the ministry "
    "produced the workbook that was loaded."
)

years = load(queries.budget_years)
if not years:
    st.warning("Gold has no budget execution yet. Load a MINFIN workbook first.")
    st.stop()

year = st.selectbox("Fiscal year", years)
budget = load(queries.budget_by_entity, year)

current_kpi, accrued_kpi, paid_kpi = st.columns(3)
current_kpi.metric("Current budget", millions(budget["current_budget"].sum(), "Q"))
accrued_kpi.metric(
    "Accrued",
    millions(budget["accrued"].sum(), "Q"),
    f"{budget['accrued'].sum() / budget['current_budget'].sum():.1%} of the budget",
    delta_color="off",
    delta_arrow="off",
)
paid_kpi.metric("Paid", millions(budget["paid"].sum(), "Q"))

budget = in_millions(budget, AMOUNTS)

st.subheader("How much of its budget each entity accrued")
st.altair_chart(execution_bars(budget), width="stretch")

st.subheader("Budget and awards per entity")
st.dataframe(
    budget,
    hide_index=True,
    column_config={
        "entity_name": "Entity",
        "current_budget": st.column_config.NumberColumn("Current budget (million Q)", format="%.1f"),
        "accrued": st.column_config.NumberColumn("Accrued (million Q)", format="%.1f"),
        "paid": st.column_config.NumberColumn("Paid (million Q)", format="%.1f"),
        "execution_rate": st.column_config.NumberColumn("Accrued share", format="percent"),
        "awarded": st.column_config.NumberColumn("Awarded (million Q)", format="%.1f"),
    },
)
st.caption(
    "Awarded is the amount of the valid awards the entity made that year in "
    "Guatecompras. The comparison is indicative: an award is a promise to pay, "
    "possibly over several years, while the accrued budget is what was "
    "received in the year, salaries included. Entities without awards, such as "
    "debt service, do not buy through Guatecompras."
)
