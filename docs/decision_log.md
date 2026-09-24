# Decision Log

## 2026-09-24: Use session-level funnel as primary analytical unit

Decision: The primary funnel will be measured at the `user_session` level.

Reason: The business question is where shoppers drop off during a visit:
view -> cart -> purchase. Session-level analysis aligns with UX, checkout,
and conversion optimization decisions.

Alternative considered: User-level funnel.

Rejected because: User-level attribution is more complex and can blur separate
shopping missions. It will remain a secondary analysis.

---

## 2026-09-24: Treat `remove_from_cart` as diagnostic, not a funnel stage

Decision: `remove_from_cart` will not be included as a forward funnel stage.

Reason: The commercial funnel is view -> cart -> purchase. Cart removal is a
behavioral friction signal, not a progression stage.

Business value: Allows distinction between users who abandon cart silently and
users who actively remove items, which may indicate price sensitivity,
comparison behavior, or insufficient product information.

---

## 2026-09-24: Use DuckDB as primary transformation engine

Decision: DuckDB will be used for large-scale event aggregation and SQL-based
pipeline development.

Reason: The dataset is large enough that plain Pandas may become awkward.
DuckDB allows SQL-first transformation, efficient local execution, and easy
integration with Python.

Alternative considered: Polars, PySpark, plain Pandas.

Future option: If the project needs heavier distributed processing, PySpark can
be introduced, but DuckDB is sufficient and more portfolio-friendly for this
scale.

---

## 2026-09-24: Do not commit raw data

Decision: Raw Kaggle files will be stored in `data/raw/` and ignored by Git.

Reason: Raw files are large, potentially licensed, and not suitable for repository
version control. A small sample dataset will be committed later for reproducibility
and tests.

---

## 2026-09-24: Use Streamlit for deployable dashboard

Decision: Streamlit will be used for the interactive portfolio dashboard.

Reason: It produces a clickable, recruiter-friendly web app from Python code and
deploys easily to free hosting.

Alternative considered: Power BI, Tableau.

Future option: Aggregated CSV outputs can also be connected to Power BI or Tableau
if a BI-tool-specific deliverable is desired.