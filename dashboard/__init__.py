"""
Streamlit placeholder for the e-commerce funnel dashboard.
"""

import streamlit as st

st.set_page_config(
    page_title="E-commerce Browse-to-Buy Funnel",
    page_icon="🛒",
    layout="wide",
)

st.title("E-commerce Browse-to-Buy Funnel Analysis")

st.caption(
    "Portfolio project: identifying where online store sessions leak value "
    "between product views, cart additions, and purchases."
)

st.divider()

st.subheader("Project Status")

st.info(
    "Phase 2 complete: repository structure, environment management, "
    "version control, and dashboard scaffold are in place."
)

st.markdown("""
    ### Planned dashboard sections

    1. Executive KPIs
       - Viewed sessions
       - Purchase conversion rate
       - Revenue per viewed session
       - Cart abandonment rate

    2. Funnel visualization
       - Product view
       - Add to cart
       - Purchase

    3. Bottleneck decomposition
       - Relative drop-off by stage
       - Absolute lost sessions by stage
       - Estimated revenue at risk

    4. Segment analysis
       - Category performance
       - Price-band performance
       - Metadata completeness
       - Cart removal behavior

    5. Recommendations
       - Where the business should intervene first
       - What experiment should be run next
    """)

st.warning(
    "This dashboard is currently a scaffold. Data pipeline, funnel logic, "
    "statistical analysis, and visualizations will be added in later phases."
)
