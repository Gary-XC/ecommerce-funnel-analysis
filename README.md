# eCommerce Conversion Funnel Optimization

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://funnel-analysis-ecommerce.streamlit.app/)
[![Python 3.10](https://img.shields.io/badge/python-3.10-blue.svg)](https://www.python.org/downloads/release/python-3100/)

## Executive Summary
This project analyzes a massive eCommerce dataset to identify critical bottlenecks in the user purchasing journey. By processing millions of event records, I discovered that the most significant revenue leak occurs at the "Added to Cart" stage. I engineered an automated data pipeline to aggregate this data and deployed an interactive dashboard that allows stakeholders to drill down into cart abandonment rates by product category and brand. 

**Live Dashboard:** [View Interactive App Here](https://funnel-analysis-ecommerce.streamlit.app/)

## Business Impact & Recommendations
Based on the funnel analysis and statistical testing, I recommend the following business actions:
* **Address Checkout Friction:** The overall cart abandonment rate is disproportionately high compared to industry averages. The product team should implement an A/B test on a simplified, single-page checkout flow.
* **Targeted Retargeting:** High-ticket items (e.g., Apple products) showed a statistically higher abandonment rate than mid-tier brands. Marketing should trigger automated "abandoned cart" email discounts specifically for items priced over $500.
* **1-Click Checkout Expansion:** Data anomalies revealed a segment of successful purchases bypassing the traditional cart. Expanding "Buy It Now" functionality across more categories could capture high-intent users before they drop off.


## Methodology & Tool Justifications
To move beyond basic Jupyter Notebooks, I engineered a production-style workflow:
* **DuckDB & Polars:** Instead of loading a 5GB+ raw CSV into Pandas (which causes memory crashes), I used DuckDB to stream and aggregate the data via SQL natively. Polars was then used for downstream metric calculations due to its multi-threaded performance. 
* **Statistical Rigor:** I conducted a **Two-Proportion Z-Test** using `statsmodels` to mathematically prove that high-ticket brands (Apple) have a significantly different cart abandonment rate than lower-ticket brands (Samsung), yielding a p-value < 0.05.
* **CI/CD Integration:** I implemented `pytest` alongside GitHub Actions to validate data quality. This caught a critical edge case ("Buy It Now" checkouts) that would have otherwise artificially inflated conversion metrics.
* **Dashboard UX:** The Streamlit app was explicitly designed using the "F-Pattern" of visual hierarchy: Big-Ass Numbers (BANs) at the top, visual trends (Plotly) in the middle, and granular data tables at the bottom right.

## Data Limitations & Caveats
* **Observational Data:** This dataset represents observational user behavior. While we can see *where* users drop off, we cannot definitively prove *why* without controlled A/B testing.
* **Data Imputation:** Users utilizing 1-click checkouts generated `purchase` events without preceding `cart` events. I programmatically inferred cart events for these users to maintain logical funnel integrity, which assumes all purchases represent an intent to cart.
* **Session Breakage:** Cross-device tracking (e.g., viewing on mobile, purchasing on desktop) is a known limitation in event logging that may slightly under report overall conversion rates.