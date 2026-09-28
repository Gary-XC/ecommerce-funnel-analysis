"""
Diagnostic script for the e-commerce funnel pipeline.

This script inspects the processed DuckDB database and helps answer:
- Are remove_from_cart events present?
- Why are removals after strict cart zero?
- How large is the non-strict purchase population?
- Should we use strict funnel, inclusive funnel, or both?



"""

from pathlib import Path

import duckdb

from ecommerce_funnel.config import PROCESSED_DATA_DIR

DB_PATH = PROCESSED_DATA_DIR / "ecommerce_funnel.duckdb"


QUERIES: dict[str, str] = {
    "Event Type Distribution": """
        SELECT
            event_type,
            COUNT(*) AS event_count,
            COUNT(DISTINCT user_session) AS session_count
        FROM events_clean
        GROUP BY event_type
        ORDER BY event_count DESC
    """,
    "Remove From Cart Existence": """
        SELECT
            COUNT(*) AS remove_event_count,
            COUNT(DISTINCT user_session) AS remove_session_count
        FROM events_clean
        WHERE event_type = 'remove_from_cart'
    """,
    "Removal Timing vs Cart Events": """
        WITH firsts AS (
            SELECT
                user_session,
                MIN(CASE WHEN event_type = 'view' THEN event_time END)
                    AS first_view_time,
                MIN(CASE WHEN event_type = 'cart' THEN event_time END)
                    AS first_cart_any_time
            FROM events_clean
            GROUP BY user_session
        ),
        cart_after_view AS (
            SELECT
                ec.user_session,
                MIN(ec.event_time) AS first_cart_time
            FROM events_clean ec
            JOIN firsts f
                ON ec.user_session = f.user_session
            WHERE ec.event_type = 'cart'
              AND f.first_view_time IS NOT NULL
              AND ec.event_time >= f.first_view_time
            GROUP BY ec.user_session
        ),
        removes AS (
            SELECT
                user_session,
                MIN(event_time) AS first_remove_time,
                COUNT(*) AS remove_count
            FROM events_clean
            WHERE event_type = 'remove_from_cart'
            GROUP BY user_session
        )
        SELECT
            COUNT(*) AS remove_sessions,
            SUM(CASE WHEN f.first_cart_any_time IS NOT NULL THEN 1 ELSE 0 END)
                AS remove_sessions_with_any_cart,
            SUM(CASE WHEN cav.first_cart_time IS NOT NULL THEN 1 ELSE 0 END)
                AS remove_sessions_with_cart_after_view,
            SUM(
                CASE
                    WHEN f.first_cart_any_time IS NOT NULL
                     AND r.first_remove_time >= f.first_cart_any_time
                    THEN 1 ELSE 0
                END
            ) AS remove_after_any_cart,
            SUM(
                CASE
                    WHEN cav.first_cart_time IS NOT NULL
                     AND r.first_remove_time >= cav.first_cart_time
                    THEN 1 ELSE 0
                END
            ) AS remove_after_strict_cart,
            SUM(
                CASE
                    WHEN f.first_cart_any_time IS NOT NULL
                     AND r.first_remove_time < f.first_cart_any_time
                    THEN 1 ELSE 0
                END
            ) AS remove_before_any_cart,
            SUM(CASE WHEN f.first_cart_any_time IS NULL THEN 1 ELSE 0 END)
                AS remove_without_any_cart
        FROM removes r
        JOIN firsts f
            ON r.user_session = f.user_session
        LEFT JOIN cart_after_view cav
            ON r.user_session = cav.user_session
    """,
    "Sample Remove Sessions": """
        WITH sample_sessions AS (
            SELECT DISTINCT user_session
            FROM events_clean
            WHERE event_type = 'remove_from_cart'
            LIMIT 10
        )
        SELECT
            ec.user_session,
            ec.event_time,
            ec.event_type,
            ec.product_id,
            ec.price
        FROM events_clean ec
        JOIN sample_sessions ss
            ON ec.user_session = ss.user_session
        ORDER BY
            ec.user_session,
            ec.event_time
    """,
    "Purchase Path Segmentation": """
        SELECT
            CASE
                WHEN has_purchase_after_cart THEN 'strict_view_cart_purchase'
                WHEN has_purchase_any THEN 'purchase_without_strict_path'
                ELSE 'no_purchase'
            END AS purchase_path,
            COUNT(*) AS sessions,
            SUM(CASE WHEN has_view THEN 1 ELSE 0 END) AS viewed_sessions,
            SUM(revenue_proxy) AS revenue_proxy
        FROM session_funnel
        GROUP BY 1
        ORDER BY sessions DESC
    """,
    "Strict vs Inclusive Conversion Rates": """
        SELECT
            SUM(CASE WHEN has_view THEN 1 ELSE 0 END) AS viewed_sessions,
            SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END) AS carted_sessions,
            SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END)
                AS strict_purchased_sessions,
            SUM(CASE WHEN has_view AND has_purchase_any THEN 1 ELSE 0 END)
                AS viewed_purchased_any_sessions,
            CAST(
                SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN has_view THEN 1 ELSE 0 END), 0)
                AS view_to_cart_rate,
            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN has_cart_after_view THEN 1 ELSE 0 END), 0)
                AS cart_to_strict_purchase_rate,
            CAST(
                SUM(CASE WHEN has_purchase_after_cart THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN has_view THEN 1 ELSE 0 END), 0)
                AS strict_overall_purchase_rate,
            CAST(
                SUM(CASE WHEN has_view AND has_purchase_any THEN 1 ELSE 0 END) AS DOUBLE
            ) / NULLIF(SUM(CASE WHEN has_view THEN 1 ELSE 0 END), 0)
                AS inclusive_overall_purchase_rate
        FROM session_funnel
    """,
    "Non-Strict Purchase Subtypes": """
        SELECT
            SUM(
                CASE
                    WHEN has_view
                     AND has_purchase_any
                     AND NOT has_purchase_after_cart
                    THEN 1 ELSE 0
                END
            ) AS viewed_non_strict_purchases,
            SUM(CASE WHEN has_view AND has_purchase_without_cart THEN 1 ELSE 0 END)
                AS viewed_purchase_without_cart,
            SUM(CASE WHEN has_view AND has_purchase_before_any_cart THEN 1 ELSE 0 END)
                AS viewed_purchase_before_cart,
            SUM(
                CASE
                    WHEN has_view
                     AND has_cart_after_view = FALSE
                     AND has_purchase_any
                    THEN 1 ELSE 0
                END
            ) AS viewed_purchase_without_cart_after_view,
            SUM(CASE WHEN NOT has_view AND has_purchase_any THEN 1 ELSE 0 END)
                AS non_viewed_purchases
        FROM session_funnel
    """,
    "Sessions Without View": """
        SELECT
            COUNT(*) AS total_sessions,
            SUM(CASE WHEN has_view THEN 1 ELSE 0 END) AS viewed_sessions,
            SUM(CASE WHEN NOT has_view THEN 1 ELSE 0 END) AS non_viewed_sessions,
            SUM(CASE WHEN NOT has_view AND has_purchase_any THEN 1 ELSE 0 END)
                AS non_viewed_purchases
        FROM session_funnel
    """,
}


def main() -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"DuckDB database not found: {DB_PATH}. " "Run the pipeline first."
        )

    print(f"Opening database: {DB_PATH}")

    try:
        con = duckdb.connect(str(DB_PATH), read_only=True)
    except Exception as exc:
        print(
            "Read-only connection failed. "
            "Attempting read-write connection in case WAL recovery is needed."
        )
        print(f"Read-only error: {exc}")
        con = duckdb.connect(str(DB_PATH))

    try:
        for title, sql in QUERIES.items():
            print(f"\n=== {title} ===")
            df = con.sql(sql).df()
            print(df.to_string(index=False))
    finally:
        con.close()


if __name__ == "__main__":
    main()
