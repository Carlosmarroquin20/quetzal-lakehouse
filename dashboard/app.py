"""Entry point of the dashboard: `streamlit run app.py`."""

import streamlit as st

st.set_page_config(page_title="Quetzal lakehouse", layout="wide")

page = st.navigation(
    [
        st.Page("views/awards.py", title="Awards", default=True),
    ]
)
page.run()
