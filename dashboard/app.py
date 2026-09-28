import os

import streamlit as st
import polars as pl
import plotly.graph_objects as go

# 1. Page Configuration (Wide layout for executive dashboards)
st.set_page_config(page_title="eCommerce Funnel Analysis", layout="wide")


# 2. Load Data Safely
@st.cache_data
def load_data():
    # the parquet file was moved into the dashboard directory for uploading to streamlit cloud
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Construct the full path to the parquet file
    file_path = os.path.join(current_dir, "funnel_aggregates.parquet")
    return pl.read_parquet(file_path)


df = load_data()

# 3. Sidebar: Non-Technical Stakeholder Controls
st.sidebar.header("Filter Options")
st.sidebar.write("Drill down to identify specific bottlenecks.")

# Dynamic Category Filter
category_list = df["category_code"].drop_nulls().unique().sort().to_list()
selected_category = st.sidebar.selectbox(
    "Select Product Category", ["All"] + category_list
)

# Apply Category Filter
if selected_category != "All":
    df_filtered = df.filter(pl.col("category_code") == selected_category)
else:
    df_filtered = df

# Dynamic Brand Filter (Updates based on category)
brand_list = df_filtered["brand"].drop_nulls().unique().sort().to_list()
selected_brand = st.sidebar.selectbox("Select Brand", ["All"] + brand_list)

# Apply Brand Filter
if selected_brand != "All":
    df_filtered = df_filtered.filter(pl.col("brand") == selected_brand)

# 4. Top Row: BANs (Big-Ass Numbers)
st.title("eCommerce Conversion Funnel")
st.markdown("Identifying user drop-off points to optimize checkout workflows.")

total_views = df_filtered["unique_views"].sum()
total_carts = df_filtered["adjusted_carts"].sum()
total_purchases = df_filtered["unique_purchases"].sum()

# Safe metric calculations (handling edge cases where filters return 0)
conv_rate = (total_purchases / total_views) * 100 if total_views > 0 else 0
abandon_rate = (
    ((total_carts - total_purchases) / total_carts) * 100 if total_carts > 0 else 0
)

# Display BANs across the top
col1, col2, col3 = st.columns(3)
col1.metric("Total Unique Views", f"{total_views:,}")
col2.metric("Overall Conversion Rate", f"{conv_rate:.2f}%")
col3.metric(
    "Cart Abandonment Rate",
    f"{abandon_rate:.2f}%",
    delta="Critical KPI",
    delta_color="inverse",
)

st.divider()

# 5. Middle/Bottom Layout: Visuals and Granular Data
col_chart, col_data = st.columns([2, 1])

with col_chart:
    st.subheader("Funnel Visualization")
    fig = go.Figure(
        go.Funnel(
            y=["Product Viewed", "Added to Cart", "Purchased"],
            x=[total_views, total_carts, total_purchases],
            textinfo="value+percent initial",
            marker={
                "color": ["#1f77b4", "#ff7f0e", "#d62728"]
            },  # Red at the bottom draws attention to the bottleneck
        )
    )
    fig.update_layout(margin=dict(l=20, r=20, t=20, b=20))
    st.plotly_chart(fig, use_container_width=True)

with col_data:
    st.subheader("Brand Breakdown")
    st.markdown("Top brands by purchase volume.")

    # Granular table for deep-dives
    table_data = (
        df_filtered.select(["brand", "unique_purchases", "overall_conversion_rate"])
        .sort("unique_purchases", descending=True)
        .head(10)
        .to_pandas()  # Streamlit handles Pandas slightly better for native dataframe rendering
    )

    # Format the conversion rate for better readability
    table_data["overall_conversion_rate"] = (
        table_data["overall_conversion_rate"] * 100
    ).round(2).astype(
        str
    ) + "%"  # type: ignore

    st.dataframe(table_data, use_container_width=True, hide_index=True)
