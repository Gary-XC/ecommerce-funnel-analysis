"""
Pipeline module for building e-commerce browse-to-buy funnel tables.

Design choices:
- DuckDB is used because the raw event files are large (~14 GB total).
- Raw CSVs are never modified.
- All transformations are reproducible from raw -> clean -> funnel tables.
- The primary analytical unit is user_session.
- The secondary analytical unit is user_session + product_id.

Business purpose:
This module converts behavioral event logs into decision-ready funnel facts:
- Which sessions viewed products?
- Which sessions added products to cart after viewing?
- Which sessions purchased after adding to cart?
- Where are the largest drop-offs?
- Which categories, price bands, and metadata conditions correlate with conversion?
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from .config import PROCESSED_DATA_DIR, RAW_DATA_DIR, ensure_data_dirs

DEFAULT_MEMORY_LIMIT = "8GB"
DEFAULT_THREADS = 4

KNOWN_EVENT_TYPES = (
    "view",
    "cart",
    "remove_from_cart",
    "purchase",
)

RAW_EVENT_COLUMNS = (
    "event_time",
    "event_type",
    "product_id",
    "category_id",
    "category_code",
    "brand",
    "price",
    "user_id",
    "user_session",
    "filename",
)


def _quote_sql_path(path: str | Path) -> str:
    """
    Safely quote a filesystem path for inclusion in DuckDB SQL.

    This avoids breakage if a path contains a single quote.
    """
    escaped = str(path).replace("'", "''")
    return f"'{escaped}'"


def get_connection(
    database: str | Path | None = None,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
) -> duckdb.DuckDBPyConnection:
    """
    Create a DuckDB connection with sensible analytics defaults.

    Why this matters:
    - Centralizes performance settings.
    - Avoids scattered hard-coded connection logic.
    - Makes local runs reproducible.
    """
    if database is None:
        ensure_data_dirs()
        database = PROCESSED_DATA_DIR / "ecommerce_funnel.duckdb"

    con = duckdb.connect(str(database))

    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute(f"SET threads TO {threads}")
    con.execute("SET preserve_insertion_order=false")

    return con


def discover_raw_csvs(raw_dir: Path = RAW_DATA_DIR) -> list[str]:
    """
    Discover raw CSV files in data/raw.

    Business/data-governance reason:
    - Raw files remain immutable.
    - Pipeline inputs are explicit and reproducible.
    """
    files = sorted(str(path) for path in raw_dir.glob("*.csv"))

    if not files:
        raise FileNotFoundError(
            f"No CSV files found in {raw_dir}. Download the Kaggle dataset into data/raw first."
        )

    return files


def register_raw_events(
    con: duckdb.DuckDBPyConnection,
    files: list[str],
) -> None:
    """
    Register raw CSV files as a DuckDB view called raw_events.

    Why read as VARCHAR first?
    - Large real-world CSVs often contain messy values.
    - Casting later with TRY_CAST lets us identify bad rows instead of failing blindly.
    - This is more production-minded than assuming every field is perfectly typed.
    """
    file_list = ", ".join(_quote_sql_path(Path(file).resolve()) for file in files)

    sql = f"""
        CREATE OR REPLACE VIEW raw_events AS
        SELECT *
        FROM read_csv(
            [{file_list}],
            header = true,
            filename = true,
            columns = {{
                event_time: 'VARCHAR',
                event_type: 'VARCHAR',
                product_id: 'VARCHAR',
                category_id: 'VARCHAR',
                category_code: 'VARCHAR',
                brand: 'VARCHAR',
                price: 'VARCHAR',
                user_id: 'VARCHAR',
                user_session: 'VARCHAR'
            }},
            ignore_errors = false,
            null_padding = true
        )
    """

    con.execute(sql)


def build_events_clean(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build the cleaned event table.

    Cleaning rules:
    1. Keep only known event types.
    2. Cast timestamps, IDs, and price safely.
    3. Require non-null event_time, user_session, and product_id.
    4. Normalize category_code and brand, preserving missingness as NULL.
    5. Deduplicate exact non-purchase events.
    6. Preserve duplicate purchase events because the dataset documentation says
       multiple purchase events per session can represent a single order.

    Business justification for duplicate handling:
    - Exact duplicate view/cart/remove events are often telemetry noise.
    - Purchase events are revenue-bearing. Since there is no quantity field,
      collapsing duplicate purchases could understate order value. We preserve them
      and document the assumption.
    """
    sql = """
        CREATE OR REPLACE TABLE events_clean AS
        WITH typed AS (
            SELECT
                TRY_CAST(event_time AS TIMESTAMP) AS event_time,
                LOWER(TRIM(event_type)) AS event_type,
                TRY_CAST(product_id AS BIGINT) AS product_id,
                TRY_CAST(category_id AS BIGINT) AS category_id,
                NULLIF(TRIM(category_code), '') AS category_code,
                NULLIF(LOWER(TRIM(brand)), '') AS brand,
                TRY_CAST(price AS DOUBLE) AS price,
                TRY_CAST(user_id AS BIGINT) AS user_id,
                TRIM(user_session) AS user_session,
                filename
            FROM raw_events
            WHERE LOWER(TRIM(event_type)) IN (
                'view',
                'cart',
                'remove_from_cart',
                'purchase'
            )
        ),
        valid AS (
            SELECT *
            FROM typed
            WHERE event_time IS NOT NULL
              AND user_session IS NOT NULL
              AND user_session <> ''
              AND product_id IS NOT NULL
        ),
        non_purchase_ranked AS (
            SELECT
                *,
                row_number() OVER (
                    PARTITION BY
                        event_time,
                        event_type,
                        product_id,
                        user_id,
                        user_session,
                        price,
                        category_id,
                        category_code,
                        brand
                    ORDER BY filename, event_time
                ) AS rn
            FROM valid
            WHERE event_type <> 'purchase'
        ),
        non_purchase_deduped AS (
            SELECT * EXCLUDE (rn)
            FROM non_purchase_ranked
            WHERE rn = 1
        ),
        purchases AS (
            SELECT *
            FROM valid
            WHERE event_type = 'purchase'
        )
        SELECT *
        FROM non_purchase_deduped

        UNION ALL

        SELECT *
        FROM purchases
    """

    con.execute(sql)


def build_session_funnel(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build the primary session-level funnel table.

    Primary funnel:
        view -> cart after view -> purchase after cart

    Important analytical distinction:
    - A session may contain many events.
    - We do not merely check whether event types exist.
    - We enforce chronological order so the funnel reflects a real journey.

    Business meaning:
    - has_view: session entered the consideration funnel.
    - has_cart_after_view: session showed purchase intent after viewing.
    - has_purchase_after_cart: session completed the intended conversion path.
    - has_removal_after_cart: session exhibited hesitation or rejection behavior.
    - has_purchase_without_strict_conversion: session purchased but not through the
      intended view -> cart -> purchase path, useful for data-quality review.
    """
    sql = """
        CREATE OR REPLACE TABLE session_funnel AS
        WITH base AS (
            SELECT
                user_session,

                MIN(CASE WHEN event_type = 'view' THEN event_time END)
                    AS first_view_time,

                MIN(CASE WHEN event_type = 'cart' THEN event_time END)
                    AS first_cart_any_time,

                MIN(CASE WHEN event_type = 'purchase' THEN event_time END)
                    AS first_purchase_any_time,

                MIN(CASE WHEN event_type = 'remove_from_cart' THEN event_time END)
                    AS first_remove_any_time,

                MIN(event_time) AS first_event_time,
                MAX(event_time) AS last_event_time,

                COUNT(CASE WHEN event_type = 'view' THEN 1 END) AS view_count,
                COUNT(CASE WHEN event_type = 'cart' THEN 1 END) AS cart_count,
                COUNT(CASE WHEN event_type = 'remove_from_cart' THEN 1 END)
                    AS remove_count,
                COUNT(CASE WHEN event_type = 'purchase' THEN 1 END)
                    AS purchase_count,

                COUNT(DISTINCT CASE WHEN event_type = 'view' THEN product_id END)
                    AS unique_products_viewed,

                COUNT(DISTINCT CASE WHEN event_type = 'cart' THEN product_id END)
                    AS unique_products_carted,

                COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN product_id END)
                    AS unique_products_purchased,

                SUM(CASE WHEN event_type = 'purchase' THEN price END)
                    AS revenue_proxy

            FROM events_clean
            GROUP BY user_session
        ),

        cart_after_view AS (
            SELECT
                ec.user_session,
                MIN(ec.event_time) AS first_cart_time
            FROM events_clean ec
            JOIN base b
                ON ec.user_session = b.user_session
            WHERE ec.event_type = 'cart'
              AND b.first_view_time IS NOT NULL
              AND ec.event_time >= b.first_view_time
            GROUP BY ec.user_session
        ),

        purchase_after_cart AS (
            SELECT
                ec.user_session,
                MIN(ec.event_time) AS first_purchase_time
            FROM events_clean ec
            JOIN cart_after_view cav
                ON ec.user_session = cav.user_session
            WHERE ec.event_type = 'purchase'
              AND ec.event_time >= cav.first_cart_time
            GROUP BY ec.user_session
        ),

        remove_after_cart AS (
            SELECT
                ec.user_session,
                MIN(ec.event_time) AS first_remove_time,
                COUNT(*) AS remove_after_cart_count
            FROM events_clean ec
            JOIN cart_after_view cav
                ON ec.user_session = cav.user_session
            WHERE ec.event_type = 'remove_from_cart'
              AND ec.event_time >= cav.first_cart_time
            GROUP BY ec.user_session
        )

        SELECT
            b.user_session,

            CAST(
                COALESCE(
                    b.first_view_time,
                    b.first_event_time
                ) AS DATE
            ) AS session_date,

            b.first_event_time,
            b.first_view_time,
            cav.first_cart_time,
            pac.first_purchase_time,
            rac.first_remove_time,

            b.first_cart_any_time,
            b.first_purchase_any_time,
            b.first_remove_any_time,
            b.last_event_time,

            (b.first_view_time IS NOT NULL) AS has_view,
            (cav.first_cart_time IS NOT NULL) AS has_cart_after_view,
            (pac.first_purchase_time IS NOT NULL) AS has_purchase_after_cart,

            (b.first_purchase_any_time IS NOT NULL) AS has_purchase_any,

            CASE
                WHEN b.first_purchase_any_time IS NOT NULL
                 AND pac.first_purchase_time IS NULL
                THEN TRUE
                ELSE FALSE
            END AS has_purchase_without_strict_conversion,

            CASE
                WHEN b.first_purchase_any_time IS NOT NULL
                 AND b.first_cart_any_time IS NULL
                THEN TRUE
                ELSE FALSE
            END AS has_purchase_without_cart,

            CASE
                WHEN b.first_purchase_any_time IS NOT NULL
                 AND (
                        b.first_cart_any_time IS NULL
                     OR b.first_purchase_any_time < b.first_cart_any_time
                     )
                THEN TRUE
                ELSE FALSE
            END AS has_purchase_before_any_cart,

            (rac.first_remove_time IS NOT NULL) AS has_removal_after_cart,

            b.view_count,
            b.cart_count,
            b.remove_count,
            b.purchase_count,
            COALESCE(rac.remove_after_cart_count, 0) AS remove_after_cart_count,

            b.unique_products_viewed,
            b.unique_products_carted,
            b.unique_products_purchased,

            COALESCE(b.revenue_proxy, 0.0) AS revenue_proxy,

            DATE_DIFF('second', b.first_view_time, cav.first_cart_time)
                AS time_to_cart_seconds,

            DATE_DIFF('second', b.first_view_time, pac.first_purchase_time)
                AS time_to_purchase_seconds,

            DATE_DIFF('second', b.first_event_time, b.last_event_time)
                AS session_duration_seconds

        FROM base b
        LEFT JOIN cart_after_view cav
            ON b.user_session = cav.user_session
        LEFT JOIN purchase_after_cart pac
            ON b.user_session = pac.user_session
        LEFT JOIN remove_after_cart rac
            ON b.user_session = rac.user_session
    """

    con.execute(sql)


def build_product_session_funnel(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build product-session-level funnel table.

    Analytical unit:
        user_session + product_id

    Why this matters:
    Session-level funnel answers:
        "Did this visit convert?"

    Product-session funnel answers:
        "Which products received attention but failed to convert?"

    This is critical for merchandising, pricing, product-page optimization, and
    category management.
    """
    sql = """
        CREATE OR REPLACE TABLE product_session_funnel AS
        WITH base AS (
            SELECT
                user_session,
                product_id,

                MIN(CASE WHEN event_type = 'view' THEN event_time END)
                    AS first_view_time,

                MIN(CASE WHEN event_type = 'cart' THEN event_time END)
                    AS first_cart_any_time,

                MIN(CASE WHEN event_type = 'purchase' THEN event_time END)
                    AS first_purchase_any_time,

                MIN(CASE WHEN event_type = 'remove_from_cart' THEN event_time END)
                    AS first_remove_any_time,

                MIN(event_time) AS first_event_time,
                MAX(event_time) AS last_event_time,

                MAX(CASE WHEN category_id IS NOT NULL THEN category_id END)
                    AS category_id,

                MAX(CASE WHEN category_code IS NOT NULL THEN category_code END)
                    AS category_code,

                MAX(CASE WHEN brand IS NOT NULL THEN brand END)
                    AS brand,

                AVG(price) AS avg_price,

                SUM(CASE WHEN event_type = 'purchase' THEN price END)
                    AS revenue_proxy,

                COUNT(CASE WHEN event_type = 'view' THEN 1 END) AS view_count,
                COUNT(CASE WHEN event_type = 'cart' THEN 1 END) AS cart_count,
                COUNT(CASE WHEN event_type = 'remove_from_cart' THEN 1 END)
                    AS remove_count,
                COUNT(CASE WHEN event_type = 'purchase' THEN 1 END)
                    AS purchase_count

            FROM events_clean
            GROUP BY user_session, product_id
        ),

        cart_after_view AS (
            SELECT
                ec.user_session,
                ec.product_id,
                MIN(ec.event_time) AS first_cart_time
            FROM events_clean ec
            JOIN base b
                ON ec.user_session = b.user_session
               AND ec.product_id = b.product_id
            WHERE ec.event_type = 'cart'
              AND b.first_view_time IS NOT NULL
              AND ec.event_time >= b.first_view_time
            GROUP BY ec.user_session, ec.product_id
        ),

        purchase_after_cart AS (
            SELECT
                ec.user_session,
                ec.product_id,
                MIN(ec.event_time) AS first_purchase_time
            FROM events_clean ec
            JOIN cart_after_view cav
                ON ec.user_session = cav.user_session
               AND ec.product_id = cav.product_id
            WHERE ec.event_type = 'purchase'
              AND ec.event_time >= cav.first_cart_time
            GROUP BY ec.user_session, ec.product_id
        ),

        remove_after_cart AS (
            SELECT
                ec.user_session,
                ec.product_id,
                MIN(ec.event_time) AS first_remove_time,
                COUNT(*) AS remove_after_cart_count
            FROM events_clean ec
            JOIN cart_after_view cav
                ON ec.user_session = cav.user_session
               AND ec.product_id = cav.product_id
            WHERE ec.event_type = 'remove_from_cart'
              AND ec.event_time >= cav.first_cart_time
            GROUP BY ec.user_session, ec.product_id
        )

        SELECT
            b.user_session,
            b.product_id,

            CAST(
                COALESCE(
                    b.first_view_time,
                    b.first_cart_any_time,
                    b.first_purchase_any_time,
                    b.first_event_time
                ) AS DATE
            ) AS product_session_date,

            b.first_event_time,
            b.first_view_time,
            cav.first_cart_time,
            pac.first_purchase_time,
            rac.first_remove_time,

            b.first_cart_any_time,
            b.first_purchase_any_time,
            b.first_remove_any_time,
            b.last_event_time,

            COALESCE(b.category_id, -1) AS category_id,
            COALESCE(b.category_code, 'unknown') AS category_code,
            COALESCE(b.brand, 'unknown') AS brand,

            b.avg_price,

            CASE
                WHEN b.avg_price IS NULL THEN 'unknown'
                WHEN b.avg_price < 25 THEN '0-25'
                WHEN b.avg_price < 50 THEN '25-50'
                WHEN b.avg_price < 100 THEN '50-100'
                WHEN b.avg_price < 250 THEN '100-250'
                WHEN b.avg_price < 500 THEN '250-500'
                ELSE '500+'
            END AS price_band,

            (b.first_view_time IS NOT NULL) AS has_view,
            (cav.first_cart_time IS NOT NULL) AS has_cart_after_view,
            (pac.first_purchase_time IS NOT NULL) AS has_purchase_after_cart,

            (b.first_purchase_any_time IS NOT NULL) AS has_purchase_any,

            CASE
                WHEN b.first_purchase_any_time IS NOT NULL
                 AND pac.first_purchase_time IS NULL
                THEN TRUE
                ELSE FALSE
            END AS has_purchase_without_strict_conversion,

            CASE
                WHEN b.first_purchase_any_time IS NOT NULL
                 AND b.first_cart_any_time IS NULL
                THEN TRUE
                ELSE FALSE
            END AS has_purchase_without_cart,

            CASE
                WHEN b.first_purchase_any_time IS NOT NULL
                 AND (
                        b.first_cart_any_time IS NULL
                     OR b.first_purchase_any_time < b.first_cart_any_time
                     )
                THEN TRUE
                ELSE FALSE
            END AS has_purchase_before_any_cart,

            (rac.first_remove_time IS NOT NULL) AS has_removal_after_cart,

            b.view_count,
            b.cart_count,
            b.remove_count,
            b.purchase_count,
            COALESCE(rac.remove_after_cart_count, 0) AS remove_after_cart_count,

            COALESCE(b.revenue_proxy, 0.0) AS revenue_proxy,

            DATE_DIFF('second', b.first_view_time, cav.first_cart_time)
                AS time_to_cart_seconds,

            DATE_DIFF('second', b.first_view_time, pac.first_purchase_time)
                AS time_to_purchase_seconds,

            DATE_DIFF('second', b.first_event_time, b.last_event_time)
                AS product_session_duration_seconds

        FROM base b
        LEFT JOIN cart_after_view cav
            ON b.user_session = cav.user_session
           AND b.product_id = cav.product_id
        LEFT JOIN purchase_after_cart pac
            ON b.user_session = pac.user_session
           AND b.product_id = pac.product_id
        LEFT JOIN remove_after_cart rac
            ON b.user_session = rac.user_session
           AND b.product_id = rac.product_id
    """

    con.execute(sql)


def build_category_funnel_daily(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build daily category-level funnel summary.

    Business question answered:
        Which categories are good at attracting views but bad at converting them?

    This moves the project from generic funnel analysis to actionable merchandising
    insight.
    """
    sql = """
        CREATE OR REPLACE TABLE category_funnel_daily AS
        SELECT
            product_session_date AS date,
            category_code,

            COUNT(*) AS viewed_product_sessions,

            SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END)
                AS carted_product_sessions,

            SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END)
                AS purchased_product_sessions,

            SUM(CASE WHEN has_removal_after_cart THEN 1 ELSE 0 END)
                AS removed_product_sessions,

            SUM(revenue_proxy) AS revenue_proxy,

            CAST(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(COUNT(*), 0)
                AS view_to_cart_rate,

            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END),
                0
            )
                AS cart_to_purchase_rate,

            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(COUNT(*), 0)
                AS overall_purchase_rate,

            SUM(revenue_proxy) / NULLIF(COUNT(*), 0)
                AS revenue_per_viewed_product_session

        FROM product_session_funnel
        WHERE has_view
        GROUP BY
            product_session_date,
            category_code
    """

    con.execute(sql)


def build_price_band_funnel(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build price-band funnel summary.

    Business question answered:
        Does price sensitivity appear mainly before cart addition or after cart
        addition?

    This helps distinguish:
        - "Users are not interested enough to add to cart."
        from
        - "Users are interested but hesitate at final purchase."
    """
    sql = """
        CREATE OR REPLACE TABLE price_band_funnel AS
        SELECT
            price_band,

            COUNT(*) AS viewed_product_sessions,

            SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END)
                AS carted_product_sessions,

            SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END)
                AS purchased_product_sessions,

            SUM(CASE WHEN has_removal_after_cart THEN 1 ELSE 0 END)
                AS removed_product_sessions,

            SUM(revenue_proxy) AS revenue_proxy,

            CAST(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(COUNT(*), 0)
                AS view_to_cart_rate,

            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END),
                0
            )
                AS cart_to_purchase_rate,

            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(COUNT(*), 0)
                AS overall_purchase_rate,

            AVG(avg_price) AS avg_product_price

        FROM product_session_funnel
        WHERE has_view
        GROUP BY price_band
    """

    con.execute(sql)


def build_metadata_funnel(con: duckdb.DuckDBPyConnection) -> None:
    """
    Build metadata-completeness funnel summary.

    Business question answered:
        Do products with missing brand or category taxonomy convert worse?

    This is a strong data-quality-to-revenue argument. It shows that analytics is not
    only about user behavior; it is also about product catalog integrity.
    """
    sql = """
        CREATE OR REPLACE TABLE metadata_funnel AS
        SELECT
            CASE
                WHEN brand = 'unknown' THEN 'missing'
                ELSE 'present'
            END AS brand_status,

            CASE
                WHEN category_code = 'unknown' THEN 'missing'
                ELSE 'present'
            END AS category_code_status,

            COUNT(*) AS viewed_product_sessions,

            SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END)
                AS carted_product_sessions,

            SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END)
                AS purchased_product_sessions,

            SUM(CASE WHEN has_removal_after_cart THEN 1 ELSE 0 END)
                AS removed_product_sessions,

            SUM(revenue_proxy) AS revenue_proxy,

            CAST(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(COUNT(*), 0)
                AS view_to_cart_rate,

            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END),
                0
            )
                AS cart_to_purchase_rate,

            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(COUNT(*), 0)
                AS overall_purchase_rate

        FROM product_session_funnel
        WHERE has_view
        GROUP BY
            CASE
                WHEN brand = 'unknown' THEN 'missing'
                ELSE 'present'
            END,

            CASE
                WHEN category_code = 'unknown' THEN 'missing'
                ELSE 'present'
            END
    """

    con.execute(sql)


def _table_exists(con: duckdb.DuckDBPyConnection, table_name: str) -> bool:
    """
    Check whether a table exists in the current DuckDB connection.

    This makes the pipeline resilient when running quick vs. full modes.
    """
    result = con.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = ?
        """,
        [table_name],
    ).fetchone()

    return bool(result and result[0] > 0)


def export_tables_to_parquet(
    con: duckdb.DuckDBPyConnection,
    tables: list[str],
    output_dir: Path = PROCESSED_DATA_DIR,
) -> list[Path]:
    """
    Export selected tables to Parquet.

    Why Parquet?
    - Columnar format.
    - Compressed.
    - Fast for dashboard loading.
    - Better than CSV for large analytical tables.

    These outputs become the bridge between pipeline and dashboard.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    exported_paths: list[Path] = []

    for table in tables:
        if not _table_exists(con, table):
            continue

        path = output_dir / f"{table}.parquet"
        quoted_path = _quote_sql_path(path)

        con.execute(f"""
            COPY (
                SELECT * FROM {table}
            ) TO {quoted_path} (FORMAT PARQUET)
            """)

        exported_paths.append(path)

    return exported_paths


def print_pipeline_summary(con: duckdb.DuckDBPyConnection) -> None:
    """
    Print a compact pipeline summary.

    This is useful for:
    - local validation,
    - CI logs,
    - README evidence,
    - debugging large runs.
    """
    print("\n=== Pipeline Summary ===\n")

    for table in [
        "events_clean",
        "session_funnel",
        "product_session_funnel",
        "category_funnel_daily",
        "price_band_funnel",
        "metadata_funnel",
    ]:
        if _table_exists(con, table):
            count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # type: ignore
            print(f"{table}: {count:,} rows")

    if _table_exists(con, "session_funnel"):
        row = con.execute("""
            SELECT
                SUM(CASE WHEN has_view THEN 1 ELSE 0 END) AS viewed_sessions,
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END)
                    AS carted_sessions,
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END)
                    AS purchased_sessions,
                SUM(CASE WHEN has_removal_after_cart THEN 1 ELSE 0 END)
                    AS removed_sessions,
                SUM(CASE WHEN has_purchase_without_strict_conversion THEN 1 ELSE 0 END)
                    AS non_strict_purchase_sessions,
                SUM(revenue_proxy) AS revenue_proxy
            FROM session_funnel
            """).fetchone()

        (
            viewed_sessions,
            carted_sessions,
            purchased_sessions,
            removed_sessions,
            non_strict_purchase_sessions,
            revenue_proxy,
        ) = row  # type: ignore

        viewed_sessions = viewed_sessions or 0
        carted_sessions = carted_sessions or 0
        purchased_sessions = purchased_sessions or 0
        removed_sessions = removed_sessions or 0
        non_strict_purchase_sessions = non_strict_purchase_sessions or 0
        revenue_proxy = revenue_proxy or 0.0

        view_to_cart = carted_sessions / viewed_sessions if viewed_sessions else 0.0
        cart_to_purchase = purchased_sessions / carted_sessions if carted_sessions else 0.0
        overall = purchased_sessions / viewed_sessions if viewed_sessions else 0.0

        print("\n--- Session Funnel ---")
        print(f"Viewed sessions:              {viewed_sessions:,}")
        print(f"Carted sessions after view:   {carted_sessions:,}")
        print(f"Purchased sessions after cart:{purchased_sessions:,}")
        print(f"Sessions with removal:        {removed_sessions:,}")
        print(f"Non-strict purchase sessions: {non_strict_purchase_sessions:,}")
        print(f"View -> Cart rate:            {view_to_cart:.4%}")
        print(f"Cart -> Purchase rate:        {cart_to_purchase:.4%}")
        print(f"Overall purchase rate:        {overall:.4%}")
        print(f"Revenue proxy:                {revenue_proxy:,.2f}")


def run_pipeline(
    raw_dir: Path = RAW_DATA_DIR,
    processed_dir: Path = PROCESSED_DATA_DIR,
    memory_limit: str = DEFAULT_MEMORY_LIMIT,
    threads: int = DEFAULT_THREADS,
    build_product_session: bool = True,
    export_parquet: bool = True,
) -> None:
    """
    Execute the full local pipeline.

    Modes:
    - Full mode: builds session and product-session funnels plus summaries.
    - Quick mode: skips product-session tables for faster iteration.

    Why this matters:
    The raw dataset is large. A quick mode lets you validate session-level logic
    before spending time on product-session and category summaries.
    """
    ensure_data_dirs()
    processed_dir.mkdir(parents=True, exist_ok=True)

    files = discover_raw_csvs(raw_dir)
    db_path = processed_dir / "ecommerce_funnel.duckdb"

    print("Starting e-commerce funnel pipeline.")
    print(f"Raw files detected: {len(files)}")
    for file in files:
        print(f"  - {file}")
    print(f"DuckDB database: {db_path}")
    print(f"Memory limit: {memory_limit}")
    print(f"Threads: {threads}")
    print(f"Build product-session funnel: {build_product_session}")
    print()

    con = get_connection(
        database=db_path,
        memory_limit=memory_limit,
        threads=threads,
    )

    register_raw_events(con, files)
    build_events_clean(con)
    build_session_funnel(con)

    export_tables = ["session_funnel"]

    if build_product_session:
        build_product_session_funnel(con)
        build_category_funnel_daily(con)
        build_price_band_funnel(con)
        build_metadata_funnel(con)

        export_tables.extend(
            [
                "product_session_funnel",
                "category_funnel_daily",
                "price_band_funnel",
                "metadata_funnel",
            ]
        )

    print_pipeline_summary(con)

    if export_parquet:
        exported = export_tables_to_parquet(
            con=con,
            tables=export_tables,
            output_dir=processed_dir,
        )

        print("\nExported Parquet files:")
        for path in exported:
            print(f"  - {path}")

    con.close()
    print("\nPipeline complete.")
