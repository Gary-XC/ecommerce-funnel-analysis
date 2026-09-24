# E-commerce Browse-to-Buy Funnel Analysis

**Portfolio project by [Your Name]**

## Executive Summary

This project analyzes e-commerce behavioral event data to identify where online store sessions leak value between product views, cart additions, and purchases. The goal is not merely to build a funnel chart, but to diagnose the commercial bottleneck and recommend a testable intervention.

The analysis uses session-level funnel logic, category and price-band segmentation, cart-removal diagnostics, and statistical conversion testing to answer a business leadership question:

> Where should the store optimize first to improve browse-to-buy conversion?

## Live Dashboard

[Live dashboard link will be added in Phase 5.]

## Business Problem

The store generates substantial product browsing activity, but purchase conversion is inefficient. Leadership needs to determine whether the primary leakage occurs during:

- Product consideration: view -> cart
- Checkout or final decision: cart -> purchase
- Behavioral hesitation: cart -> remove_from_cart -> no purchase
- Category or pricing friction: certain products/categories underperform

## Dataset

Source: [Kaggle: E-commerce behavior data from multi-category store](https://www.kaggle.com/datasets/mkechinov/ecommerce-behavior-data-from-multi-category-store)

Event types:

- `view`
- `cart`
- `remove_from_cart`
- `purchase`

Primary analytical unit:

- `user_session`

Secondary analytical unit:

- `user_session + product_id`

## Tech Stack

- Python
- DuckDB
- Pandas
- PyArrow
- SciPy / Statsmodels
- Plotly
- Streamlit
- Git / GitHub
- GitHub Actions
- pytest
- Ruff

## Project Status

- [x] Phase 1: Business scoping and hypothesis generation
- [x] Phase 2: Repository, environment, and version control setup
- [ ] Phase 3: Data wrangling and pipeline automation
- [ ] Phase 4: EDA and statistical rigor
- [ ] Phase 5: Dashboarding and deployment
- [ ] Phase 6: Dual-audience README
- [ ] Phase 7: Resume bullet translation

## Repository Structure

```text
ecommerce-funnel-analysis/
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
├── dashboard/
├── docs/
├── notebooks/
├── scripts/
├── src/ecommerce_funnel/
├── tests/
├── .github/workflows/
├── pyproject.toml
├── Makefile
└── README.md
```