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


# The second color, for the days the source did not publish. Text says what
# they are, so the color is never the only cue.
FILLED_COLOR = "#eb6834"


def rate_line(data: pd.DataFrame) -> alt.LayerChart:
    """The daily reference rate, with the days filled in gold marked."""
    series = alt.Color(
        "series:N",
        title=None,
        scale=alt.Scale(
            domain=["Reference rate", "Day not published (filled)"],
            range=[SERIES_COLOR, FILLED_COLOR],
        ),
        legend=alt.Legend(orient="top"),
    )
    hover = alt.selection_point(
        fields=["date_day"], nearest=True, on="pointerover", empty=False
    )
    base = alt.Chart(data).encode(
        x=alt.X("date_day:T", title=None, axis=alt.Axis(format="%Y", tickCount="year")),
        y=alt.Y(
            "reference_rate:Q",
            title="Quetzales per US dollar",
            scale=alt.Scale(zero=False),
        ),
        tooltip=[
            alt.Tooltip("date_day:T", title="Day", format="%Y-%m-%d"),
            alt.Tooltip("reference_rate:Q", title="Reference rate", format=".5f"),
            alt.Tooltip("buy_rate:Q", title="Buying", format=".5f"),
            alt.Tooltip("sell_rate:Q", title="Selling", format=".5f"),
            alt.Tooltip(
                "rate_published_date:T", title="Rate published on", format="%Y-%m-%d"
            ),
        ],
    )
    line = base.transform_calculate(series="'Reference rate'").mark_line(
        strokeWidth=2
    ).encode(color=series)
    filled = (
        base.transform_filter("!datum.is_published")
        .transform_calculate(series="'Day not published (filled)'")
        .mark_point(filled=True, size=64)
        .encode(color=series)
    )
    # Invisible points pick the day nearest the pointer; a rule marks it.
    pointer = base.mark_point(opacity=0).add_params(hover)
    rule = base.mark_rule(color="gray").transform_filter(hover)
    return alt.layer(line, filled, pointer, rule)


def execution_bars(data: pd.DataFrame) -> alt.Chart:
    """Share of the current budget accrued, per entity, highest first.

    Expects the amounts already in millions of quetzales.
    """
    return (
        alt.Chart(data)
        .mark_bar(color=SERIES_COLOR, cornerRadiusEnd=4)
        .encode(
            y=alt.Y("entity_name:N", title=None, sort="-x", axis=alt.Axis(labelLimit=420)),
            x=alt.X(
                "execution_rate:Q",
                title="Accrued, share of the current budget",
                axis=alt.Axis(format="%"),
                scale=alt.Scale(domain=[0, 1]),
            ),
            tooltip=[
                alt.Tooltip("entity_name:N", title=""),
                alt.Tooltip("execution_rate:Q", title="Accrued share", format=".1%"),
                alt.Tooltip("accrued:Q", title="Accrued (million Q)", format=",.1f"),
                alt.Tooltip(
                    "current_budget:Q", title="Current budget (million Q)", format=",.1f"
                ),
            ],
        )
    )
