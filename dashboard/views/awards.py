"""Public procurement awards per year, from fct_awards."""

import streamlit as st

from quetzal_dashboard import queries
from quetzal_dashboard.cache import load
from quetzal_dashboard.charts import (
    CURRENCIES,
    in_millions,
    millions,
    monthly_bars,
    ranked_bars,
)

AMOUNTS = ["amount_gtq", "amount_usd"]

st.title("Awards")
st.caption(
    "Contracting processes of Guatecompras awarded to a supplier. Totals count "
    "valid awards only: cancelled ones are left out. Dollar amounts use the "
    "Banco de Guatemala reference rate of the day of each award."
)

years = load(queries.award_years)
if not years:
    st.warning("Gold has no awards yet. Run the pipeline first.")
    st.stop()

left, right = st.columns([1, 3])
year = left.selectbox("Year of award", years)
currency = right.radio("Amounts in", list(CURRENCIES), horizontal=True)
amount, prefix = CURRENCIES[currency]
unit = f"Million {prefix}"

totals = load(queries.award_totals, year).iloc[0]
awards_kpi, amount_kpi, cancelled_kpi = st.columns(3)
awards_kpi.metric("Valid awards", f"{int(totals['awards']):,}")
amount_kpi.metric("Amount awarded", millions(totals[amount], prefix))
cancelled_kpi.metric("Cancelled awards", f"{int(totals['cancelled_awards']):,}")
st.caption(f"Last award of {year} in gold: {totals['last_award_date']:%Y-%m-%d}.")

st.subheader("Per month")
per_month = in_millions(load(queries.awards_per_month, year), AMOUNTS)
st.altair_chart(monthly_bars(per_month, amount, unit), width="stretch")

st.subheader("By procurement procedure")
by_procedure = in_millions(load(queries.awards_by_procedure, year), AMOUNTS)
st.altair_chart(
    ranked_bars(by_procedure, "procurement_procedure", amount, unit),
    width="stretch",
)

st.subheader("Suppliers")
by_kind = in_millions(load(queries.awards_by_supplier_kind, year), AMOUNTS)
by_kind["share"] = by_kind[amount] / by_kind[amount].sum()
st.dataframe(
    by_kind[["supplier_kind", "suppliers", "awards", amount, "share"]],
    hide_index=True,
    column_config={
        "supplier_kind": "Supplier",
        "suppliers": st.column_config.NumberColumn("Suppliers", format="localized"),
        "awards": st.column_config.NumberColumn("Awards", format="localized"),
        amount: st.column_config.NumberColumn(unit, format="%.1f"),
        "share": st.column_config.NumberColumn("Share of amount", format="percent"),
    },
)
st.caption(
    "Natural persons, and suppliers whose legal type the source does not "
    "give, are pseudonymized in gold. They are only shown as a group."
)

st.markdown(f"**Legal entities awarded the most in {year}**")
top = in_millions(load(queries.top_named_suppliers, year), AMOUNTS)
st.dataframe(
    top[["supplier_name", "supplier_id", "awards", amount]],
    hide_index=True,
    column_config={
        "supplier_name": "Supplier",
        "supplier_id": "Tax number (NIT)",
        "awards": st.column_config.NumberColumn("Awards", format="localized"),
        amount: st.column_config.NumberColumn(unit, format="%.1f"),
    },
)
