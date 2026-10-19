"""Texas Grid & Weather dashboard (Streamlit).

Reads the small CSV snapshot exported by `python -m src.export_dashboard`,
so it runs anywhere (including Streamlit Community Cloud) without the warehouse.

Run locally:
    streamlit run dashboard/app.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

SNAPSHOT = Path(__file__).parent / "snapshot"
REPO_URL = "https://github.com/ramswargam1234/texas-grid-pipeline"

# Reference palette (validated): series 1 blue, series 2 orange, sequential blue ramp.
BLUE = "#2a78d6"
ORANGE = "#eb6834"
MUTED = "#8a8985"
GRID = "#e9e8e4"
SEQ_BLUE = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

st.set_page_config(page_title="Texas Grid & Weather", page_icon="⚡", layout="wide")


@st.cache_data
def load():
    def csv(name, **kw):
        return pd.read_csv(SNAPSHOT / f"{name}.csv", **kw)

    return {
        "headline": json.loads((SNAPSHOT / "headline.json").read_text()),
        "daily": csv("daily", parse_dates=["date_local"]),
        "by_temp": csv("by_temperature"),
        "hour_month": csv("hour_by_month"),
        "forecast": csv("forecast_monthly", parse_dates=["month"]),
        "freeze": csv("freeze_2021", parse_dates=["period_local"]),
        "missing": csv("missing_by_month", parse_dates=["month"]),
    }


def style(fig: go.Figure, height: int = 340, y_title: str = "", x_title: str = "") -> go.Figure:
    """Shared, recessive chart styling: light grid, no chart junk, unified hover."""
    fig.update_layout(
        height=height,
        margin=dict(l=8, r=8, t=8, b=8),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        showlegend=False,
        font=dict(size=13),
    )
    fig.update_xaxes(title=x_title, showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED))
    fig.update_yaxes(title=y_title, gridcolor=GRID, zeroline=False, tickfont=dict(color=MUTED),
                     title_font=dict(color=MUTED))
    return fig


def chart(fig, **kw):
    """Render a Plotly figure without the floating toolbar."""
    st.plotly_chart(fig, config={"displayModeBar": False}, **kw)


data = load()
h = data["headline"]
daily = data["daily"]
# Drop partial days (first/last day of the range) so peaks aren't understated.
daily = daily[daily["hours_with_demand"] >= 20]

# ---------- header ----------
st.title("⚡ Texas Grid & Weather")
st.markdown(
    f"How weather drives electricity demand on the Texas grid (ERCOT). "
    f"Hourly demand from the U.S. EIA joined with weather for Dallas, Houston, Austin and San Antonio, "
    f"**{h['first_date']} → {h['last_date']}**. "
    f"Built with Python, dbt, DuckDB and Airflow. [Source code]({REPO_URL})"
)

# ---------- headline numbers ----------
peak_time = pd.Timestamp(h["peak_time_local"])
c1, c2, c3, c4 = st.columns(4)
c1.metric("All-time peak demand", f"{h['peak_mwh']:,.0f} MWh",
          help=f"{peak_time:%b %d, %Y, %I %p} Central, avg temp {h['peak_avg_temp_f']:.0f}°F")
c1.caption(f"{peak_time:%b %d, %Y · %I %p} CT")
c2.metric("Heat sensitivity", f"+{h['heat_slope_mwh_per_f']:,.0f} MWh / °F",
          help="Slope of hourly demand vs. average Texas temperature, for hours at or above 75°F")
c2.caption("per °F above 75°F")
c3.metric("Hot vs. mild hours", f"{h['hot_vs_mild_ratio']:.2f}×",
          help="Average demand at ≥95°F divided by average demand at 65–75°F")
c3.caption("demand at ≥95°F vs. 65–75°F")
c4.metric("Day-ahead forecast error", f"{h['forecast_mape_pct']:.2f}%",
          help="Mean absolute percentage error of ERCOT's day-ahead demand forecast")
c4.caption("mean absolute % error")

st.divider()

# ---------- 1. daily peak over time ----------
st.subheader("Daily peak demand")
min_d, max_d = daily["date_local"].min().date(), daily["date_local"].max().date()
start, end = st.slider("Date range", min_value=min_d, max_value=max_d, value=(min_d, max_d),
                       format="MMM YYYY", label_visibility="collapsed")
view = daily[(daily["date_local"].dt.date >= start) & (daily["date_local"].dt.date <= end)]
fig = px.line(view, x="date_local", y="peak_demand_mwh",
              custom_data=["max_temp_f", "peak_hour_local"])
fig.update_traces(line=dict(color=BLUE, width=2),
                  hovertemplate="<b>%{y:,.0f} MWh</b> peak at %{customdata[1]}:00<br>"
                                "High temp %{customdata[0]:.0f}°F<extra></extra>")
chart(style(fig, y_title="MWh"), width="stretch")
st.caption("Summer peaks dominate: air-conditioning load drives the highest demand of the year.")

# ---------- 2 & 3 side by side ----------
left, right = st.columns(2)

with left:
    st.subheader("Demand rises with heat and cold")
    bt = data["by_temp"]
    fig = px.bar(bt, x="temp_band_f", y="avg_demand_mwh", custom_data=["hours", "max_demand_mwh"])
    fig.update_traces(marker_color=BLUE, marker_line_width=0,
                      hovertemplate="<b>%{x}–%{x}+5°F</b><br>Avg %{y:,.0f} MWh<br>"
                                    "Peak %{customdata[1]:,.0f} MWh<br>%{customdata[0]:,} hours<extra></extra>")
    fig.update_layout(bargap=0.15)
    chart(style(fig, y_title="Avg hourly demand (MWh)", x_title="Average Texas temperature (°F)"),
                    width="stretch")
    st.caption("A U-shaped curve: demand is lowest around 60–70°F and climbs for both heating and cooling.")

with right:
    st.subheader("When demand peaks, by month and hour")
    hm = data["hour_month"].pivot(index="month", columns="hour", values="avg_demand_mwh")
    fig = go.Figure(go.Heatmap(
        z=hm.values, x=[f"{c:02d}" for c in hm.columns], y=[MONTHS[m - 1] for m in hm.index],
        colorscale=SEQ_BLUE, xgap=2, ygap=2, colorbar=dict(title="MWh", thickness=10),
        hovertemplate="<b>%{y}, %{x}:00</b><br>Avg %{z:,.0f} MWh<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed")
    fig = style(fig, x_title="Hour of day (Central)")
    fig.update_layout(hovermode="closest")
    chart(fig, width="stretch")
    st.caption("Late-afternoon summer hours are the grid's most stressful window.")

# ---------- 4. Winter Storm Uri ----------
st.subheader("February 2021: Winter Storm Uri")
fz = data["freeze"]
if fz.empty:
    st.info("No data for February 2021 in this snapshot.")
else:
    st.markdown(
        "Temperatures across Texas fell below freezing for days. ERCOT ordered rolling blackouts, "
        "so measured demand reflects the power that could be delivered, not the power people needed. "
        "Compare the day-ahead forecast (orange) with actual demand (blue)."
    )
    a, b = st.columns(2)
    with a:
        fig = go.Figure()
        fig.add_scatter(x=fz["period_local"], y=fz["forecast_mwh"], name="Day-ahead forecast",
                        line=dict(color=ORANGE, width=2),
                        hovertemplate="Forecast %{y:,.0f} MWh<extra></extra>")
        fig.add_scatter(x=fz["period_local"], y=fz["demand_mwh"], name="Actual demand",
                        line=dict(color=BLUE, width=2),
                        hovertemplate="Actual %{y:,.0f} MWh<extra></extra>")
        fig = style(fig, y_title="MWh")
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.08, x=0))
        chart(fig, width="stretch")
    with b:
        fig = px.line(fz, x="period_local", y="avg_temp_f")
        fig.update_traces(line=dict(color=BLUE, width=2),
                          hovertemplate="%{y:.0f}°F avg across 4 cities<extra></extra>")
        fig.add_hline(y=32, line=dict(color=MUTED, dash="dot", width=1),
                      annotation_text="32°F", annotation_font_color=MUTED)
        chart(style(fig, y_title="Avg Texas temperature (°F)"), width="stretch")

# ---------- 5. forecast accuracy + data quality ----------
left, right = st.columns(2)
with left:
    st.subheader("Day-ahead forecast error by month")
    fc = data["forecast"]
    fig = px.line(fc, x="month", y="mape_pct", markers=True)
    fig.update_traces(line=dict(color=BLUE, width=2), marker=dict(size=8),
                      hovertemplate="<b>%{x|%b %Y}</b><br>%{y:.2f}% error<extra></extra>")
    chart(style(fig, height=280, y_title="Mean abs. % error"), width="stretch")
    st.caption("The February 2021 spike is Winter Storm Uri, when blackouts pushed actual demand far below forecast.")

with right:
    st.subheader("Data quality")
    st.markdown(
        f"- **{h['rows_modeled']:,}** rows modeled across **{h['hours']:,}** hours\n"
        f"- **{h['missing_hours']:,}** hours missing from the EIA feed, caught by a dbt test\n"
        f"- 19 automated dbt tests run on every build\n"
        f"- Snapshot exported {h['exported_at_utc'][:10]}"
    )
    miss = data["missing"]
    if not miss.empty:
        with st.expander("Missing hours by month"):
            st.dataframe(miss.assign(month=miss["month"].dt.strftime("%b %Y")),
                         hide_index=True, width="stretch")

with st.expander("View daily data as a table"):
    st.dataframe(view.sort_values("date_local", ascending=False), hide_index=True, width="stretch")

st.caption("Data: U.S. Energy Information Administration (EIA) Open Data · Open-Meteo Historical Weather API. "
           "Demand values are hourly ERCOT load in MWh; times are US Central.")
