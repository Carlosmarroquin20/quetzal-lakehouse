"""Entry point of the dashboard: `streamlit run app.py`."""

import streamlit as st

st.set_page_config(page_title="Quetzal lakehouse", layout="wide")

page = st.navigation(
    [
        st.Page("views/awards.py", title="Awards", default=True),
        st.Page("views/budget.py", title="Budget execution"),
        st.Page("views/exchange_rates.py", title="Exchange rate"),
    ]
)
page.run()
