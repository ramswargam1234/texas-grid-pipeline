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
def load(snapshot_version: float):
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
        "zones": csv("zones") if (SNAPSHOT / "zones.csv").exists() else pd.DataFrame(),
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


data = load((SNAPSHOT / "headline.json").stat().st_mtime)
h = data["headline"]
daily = data["daily"]
# Drop partial days (first/last day of the range) so peaks aren't understated.
daily = daily[daily["hours_with_demand"] >= 20]

# ---------- header ----------
st.title("⚡ Texas Grid & Weather")
st.markdown(
    f"How weather drives electricity demand on the Texas grid (ERCOT). "
    f"Hourly demand from the U.S. EIA joined with weather for Dallas, Houston, Austin and San Antonio "
    f"(plus one city per ERCOT weather zone), "
    f"**{h['first_date']} → {h['last_date']}**. "
    f"Built with Python, AWS S3, dbt, DuckDB and Airflow. [Source code]({REPO_URL})"
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
uri = h.get("uri") or {}


def num(v, spec=",.0f", suffix=""):
    return "n/a" if v is None or v != v else f"{v:{spec}}{suffix}"


if fz.empty or not uri:
    st.info("No data for February 2021 in this snapshot.")
else:
    st.markdown(
        "ERCOT ordered rolling blackouts from **1:20 AM Feb 15 to 12:42 AM Feb 18, 2021**. During those hours, "
        "measured demand shows the power the grid could deliver, not the power people needed. "
        "This estimates the gap two ways: ERCOT's own **day-ahead forecast**, and a **weather model** "
        "trained on other winters' cold hours."
    )
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Unserved energy (forecast gap)", num(uri.get("unserved_gwh_forecast"), suffix=" GWh"),
              help="Sum over load-shed hours of max(day-ahead forecast − actual demand, 0). 1 GWh = 1,000 MWh.")
    m1.caption("headline estimate")
    m2.metric("Unserved energy (weather model)", num(uri.get("unserved_gwh_weather"), suffix=" GWh"),
              help="Sum over load-shed hours of max(weather-expected demand − actual, 0). The storm was colder "
                   "than most training hours, so this extrapolates and is less certain.")
    m2.caption("upper bound: extrapolates past the coldest training hours")
    m3.metric("Largest hourly shortfall", num(uri.get("max_hourly_gap_forecast_mwh"), suffix=" MW"),
              help="Biggest single-hour gap between forecast and actual demand during load shed.")
    m3.caption("above the 20,000 MW ERCOT ordered shed")
    m4.metric("Hours of load shed", num(uri.get("shed_hours"), ",.0f"))
    m4.caption(f"coldest hour {num(uri.get('min_temp_f'), '.0f', '°F')} (4-city avg)")

    a, b = st.columns(2)
    shed = fz[fz["is_load_shed"]]
    with a:
        fig = go.Figure()
        if not shed.empty:
            fig.add_vrect(x0=shed["period_local"].min(), x1=shed["period_local"].max(),
                          fillcolor=MUTED, opacity=0.12, line_width=0,
                          annotation_text="Load shed", annotation_position="top left",
                          annotation_font_color=MUTED)
        fig.add_scatter(x=fz["period_local"], y=fz["forecast_mwh"], name="Day-ahead forecast",
                        line=dict(color=ORANGE, width=2),
                        hovertemplate="Forecast %{y:,.0f} MWh<extra></extra>")
        fig.add_scatter(x=fz["period_local"], y=fz["weather_expected_mwh"], name="Weather model",
                        line=dict(color=MUTED, width=2, dash="dot"),
                        hovertemplate="Weather model %{y:,.0f} MWh<extra></extra>")
        fig.add_scatter(x=fz["period_local"], y=fz["demand_mwh"], name="Actual demand",
                        line=dict(color=BLUE, width=2),
                        hovertemplate="Actual %{y:,.0f} MWh<extra></extra>")
        fig = style(fig, y_title="MWh")
        fig.update_layout(showlegend=True, legend=dict(orientation="h", y=1.1, x=0))
        chart(fig, width="stretch")
    with b:
        fig = px.line(fz, x="period_local", y="avg_temp_f")
        fig.update_traces(line=dict(color=BLUE, width=2),
                          hovertemplate="%{y:.0f}°F avg across 4 cities<extra></extra>")
        fig.add_hline(y=32, line=dict(color=MUTED, dash="dot", width=1),
                      annotation_text="32°F", annotation_font_color=MUTED)
        chart(style(fig, y_title="Avg Texas temperature (°F)"), width="stretch")
    st.markdown(
        f"**Validation:** the day-ahead forecast peaked at **{num(uri.get('peak_forecast_mwh'))} MW** during load shed, "
        "matching ERCOT's own estimate of about 76,800 MW of demand without blackouts. "
        f"The largest hourly gap (**{num(uri.get('max_hourly_gap_forecast_mwh'))} MW**) is above the 20,000 MW ERCOT ordered shed, "
        "so delivered power likely also fell from local outages and industrial cutbacks. "
        f"The weather model peaks at {num(uri.get('peak_weather_expected_mwh'))} MW, overshooting ERCOT's estimate, "
        "so treat it as an upper bound."
    )
    st.caption(
        "For reference, ERCOT reported shedding up to 20 GW and estimated peak demand would have reached about "
        "76.8 GW without load shed. The weather model fits one temperature slope plus a baseline for each hour "
        "of day on cold winter hours (Dec–Feb, below 50°F), excluding Feb 8–21, 2021."
    )

# ---------- 4b. ERCOT weather zones ----------
zones = data["zones"]
if not zones.empty:
    st.subheader("Which parts of Texas are most heat-sensitive?")
    st.markdown(
        "ERCOT splits its load into 8 weather zones. Each zone's demand is matched with its own local weather "
        "(for example Midland for the Permian Basin, Corpus Christi for the Southern zone). Heat sensitivity "
        "is shown as a **% of the zone's own average demand per °F above 75°F**, so large and small zones compare fairly."
    )
    zl, zr = st.columns(2)
    with zl:
        z = zones.sort_values("heat_slope_pct_per_f")
        fig = px.bar(z, x="heat_slope_pct_per_f", y="zone_label", orientation="h",
                     custom_data=["heat_slope_mwh_per_f", "share_of_energy"])
        fig.update_traces(marker_color=BLUE, marker_line_width=0,
                          hovertemplate="<b>%{y}</b><br>+%{x:.2f}% of avg demand per °F<br>"
                                        "+%{customdata[0]:,.0f} MWh per °F<br>"
                                        "%{customdata[1]:.0%} of ERCOT energy<extra></extra>")
        fig.update_layout(bargap=0.25)
        fig = style(fig, height=360, x_title="Extra demand per °F above 75°F (% of zone average)")
        fig.update_layout(hovermode="closest")
        chart(fig, width="stretch")
    with zr:
        z = zones.sort_values("share_of_energy")
        fig = px.bar(z, x="share_of_energy", y="zone_label", orientation="h",
                     custom_data=["peak_demand_mwh"])
        fig.update_traces(marker_color=MUTED, marker_line_width=0,
                          hovertemplate="<b>%{y}</b><br>%{x:.1%} of ERCOT energy<br>"
                                        "Peak %{customdata[0]:,.0f} MWh<extra></extra>")
        fig.update_layout(bargap=0.25)
        fig = style(fig, height=360, x_title="Share of ERCOT energy, 2021 to today")
        fig.update_xaxes(tickformat=".0%")
        fig.update_layout(hovermode="closest")
        chart(fig, width="stretch")
    st.caption("A dbt test checks every hour that the 8 zones add up to ERCOT's total (within 3%).")

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
        f"- 51 automated dbt tests run on every build\n"
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
