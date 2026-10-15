"""Chart and number formatting shared by the pages."""

import altair as alt
import pandas as pd

# One series per chart, so every chart uses the same single color.
SERIES_COLOR = "#2a78d6"

# What the reader picks on each page, and the column and prefix it maps to.
CURRENCIES = {
    "Quetzales": ("amount_gtq", "Q"),
    "US dollars": ("amount_usd", "US$"),
}


def millions(value: float, prefix: str) -> str:
    return f"{prefix}{value / 1e6:,.1f} M"


def in_millions(data: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """A copy with amounts in millions, the unit every page shows them in."""
    return data.assign(**{column: data[column] / 1e6 for column in columns})


def monthly_bars(data: pd.DataFrame, value: str, title: str) -> alt.Chart:
    """Bars of one measure per month, with its value on hover."""
    return (
        alt.Chart(data)
        .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4)
        .encode(
            x=alt.X("month(month):O", title=None),
            y=alt.Y(f"{value}:Q", title=title, axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip("yearmonth(month):T", title="Month", format="%B %Y"),
                alt.Tooltip(f"{value}:Q", title=title, format=",.1f"),
                alt.Tooltip("awards:Q", title="Awards", format=","),
            ],
        )
    )


def ranked_bars(data: pd.DataFrame, category: str, value: str, title: str) -> alt.Chart:
    """Horizontal bars, largest first, for categories with long names."""
    return (
        alt.Chart(data)
        .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4)
        .encode(
            y=alt.Y(
                f"{category}:N",
                title=None,
                sort="-x",
                axis=alt.Axis(labelLimit=420),
            ),
            x=alt.X(f"{value}:Q", title=title, axis=alt.Axis(format=",.0f")),
            tooltip=[
                alt.Tooltip(f"{category}:N", title=""),
                alt.Tooltip(f"{value}:Q", title=title, format=",.1f"),
                alt.Tooltip("awards:Q", title="Awards", format=","),
            ],
        )
    )
