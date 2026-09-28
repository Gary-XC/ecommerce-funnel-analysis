"""
Unit tests for funnel pipeline logic.

These tests validate the business rules before running on the full dataset.

Key behaviors tested:
- Strict chronological funnel: view -> cart -> purchase.
- Cart before view does not count as cart-after-view.
- Purchase without strict conversion is flagged.
- Cart removal after cart is flagged.
- Duplicate non-purchase events are collapsed.
- Duplicate purchase events are preserved because purchases may represent
  multiple line items in one order.
"""

import duckdb
import pytest

from ecommerce_funnel.pipeline import (
    build_events_clean,
    build_product_session_funnel,
    build_session_funnel,
)


def _create_raw_events_table(con: duckdb.DuckDBPyConnection) -> None:
    con.execute("""
        CREATE TABLE raw_events (
            event_time VARCHAR,
            event_type VARCHAR,
            product_id VARCHAR,
            category_id VARCHAR,
            category_code VARCHAR,
            brand VARCHAR,
            price VARCHAR,
            user_id VARCHAR,
            user_session VARCHAR,
            filename VARCHAR
        )
        """)


def _insert_raw_events(
    con: duckdb.DuckDBPyConnection,
    rows: list[tuple[str, ...]],
) -> None:
    con.executemany(
        """
        INSERT INTO raw_events
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )


def _get_session_row(
    con: duckdb.DuckDBPyConnection,
    user_session: str,
) -> dict:
    cursor = con.execute(
        """
        SELECT *
        FROM session_funnel
        WHERE user_session = ?
        """,
        [user_session],
    )

    columns = [description[0] for description in cursor.description]
    row = cursor.fetchone()

    if row is None:
        raise AssertionError(f"Session {user_session} not found in session_funnel.")

    return dict(zip(columns, row, strict=True))


def _get_product_session_row(
    con: duckdb.DuckDBPyConnection,
    user_session: str,
    product_id: int,
) -> dict:
    cursor = con.execute(
        """
        SELECT *
        FROM product_session_funnel
        WHERE user_session = ?
          AND product_id = ?
        """,
        [user_session, product_id],
    )

    columns = [description[0] for description in cursor.description]
    row = cursor.fetchone()

    if row is None:
        raise AssertionError(f"Product session {user_session}/{product_id} not found.")

    return dict(zip(columns, row, strict=True))


def test_strict_view_cart_purchase_funnel() -> None:
    con = duckdb.connect()
    _create_raw_events_table(con)

    _insert_raw_events(
        con,
        [
            (
                "2019-10-01 00:00:00",
                "view",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_strict",
                "test.csv",
            ),
            (
                "2019-10-01 00:01:00",
                "cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_strict",
                "test.csv",
            ),
            (
                "2019-10-01 00:02:00",
                "purchase",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_strict",
                "test.csv",
            ),
        ],
    )

    build_events_clean(con)
    build_session_funnel(con)

    row = _get_session_row(con, "sess_strict")

    assert row["has_view"] is True
    assert row["has_cart_after_view"] is True
    assert row["has_purchase_after_cart"] is True
    assert row["has_purchase_without_strict_conversion"] is False
    assert row["view_count"] == 1
    assert row["cart_count"] == 1
    assert row["purchase_count"] == 1
    assert row["revenue_proxy"] == pytest.approx(10.0)


def test_cart_before_view_does_not_count_as_cart_after_view() -> None:
    con = duckdb.connect()
    _create_raw_events_table(con)

    _insert_raw_events(
        con,
        [
            (
                "2019-10-01 00:00:00",
                "cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_cart_before_view",
                "test.csv",
            ),
            (
                "2019-10-01 00:01:00",
                "view",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_cart_before_view",
                "test.csv",
            ),
            (
                "2019-10-01 00:02:00",
                "purchase",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_cart_before_view",
                "test.csv",
            ),
        ],
    )

    build_events_clean(con)
    build_session_funnel(con)

    row = _get_session_row(con, "sess_cart_before_view")

    assert row["has_view"] is True
    assert row["has_cart_after_view"] is False
    assert row["has_purchase_after_cart"] is False
    assert row["has_purchase_without_strict_conversion"] is True


def test_purchase_before_cart_is_flagged_as_non_strict_conversion() -> None:
    con = duckdb.connect()
    _create_raw_events_table(con)

    _insert_raw_events(
        con,
        [
            (
                "2019-10-01 00:00:00",
                "purchase",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_purchase_first",
                "test.csv",
            ),
            (
                "2019-10-01 00:01:00",
                "cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_purchase_first",
                "test.csv",
            ),
            (
                "2019-10-01 00:02:00",
                "view",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_purchase_first",
                "test.csv",
            ),
        ],
    )

    build_events_clean(con)
    build_session_funnel(con)

    row = _get_session_row(con, "sess_purchase_first")

    assert row["has_view"] is True
    assert row["has_cart_after_view"] is False
    assert row["has_purchase_after_cart"] is False
    assert row["has_purchase_without_strict_conversion"] is True
    assert row["has_purchase_before_any_cart"] is True


def test_removal_after_cart_is_flagged() -> None:
    con = duckdb.connect()
    _create_raw_events_table(con)

    _insert_raw_events(
        con,
        [
            (
                "2019-10-01 00:00:00",
                "view",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_remove",
                "test.csv",
            ),
            (
                "2019-10-01 00:01:00",
                "cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_remove",
                "test.csv",
            ),
            (
                "2019-10-01 00:02:00",
                "remove_from_cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_remove",
                "test.csv",
            ),
        ],
    )

    build_events_clean(con)
    build_session_funnel(con)

    row = _get_session_row(con, "sess_remove")

    assert row["has_cart_after_view"] is True
    assert row["has_purchase_after_cart"] is False
    assert row["has_removal_after_cart"] is True
    assert row["remove_after_cart_count"] == 1


def test_duplicate_non_purchase_events_are_collapsed_but_purchases_preserved() -> None:
    con = duckdb.connect()
    _create_raw_events_table(con)

    duplicate_view = (
        "2019-10-01 00:00:00",
        "view",
        "1",
        "100",
        "electronics",
        "brand_a",
        "10.0",
        "1",
        "sess_dupes",
        "test.csv",
    )

    duplicate_purchase = (
        "2019-10-01 00:02:00",
        "purchase",
        "1",
        "100",
        "electronics",
        "brand_a",
        "10.0",
        "1",
        "sess_dupes",
        "test.csv",
    )

    _insert_raw_events(
        con,
        [
            duplicate_view,
            duplicate_view,
            (
                "2019-10-01 00:01:00",
                "cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "10.0",
                "1",
                "sess_dupes",
                "test.csv",
            ),
            duplicate_purchase,
            duplicate_purchase,
        ],
    )

    build_events_clean(con)
    build_session_funnel(con)

    row = _get_session_row(con, "sess_dupes")

    assert row["view_count"] == 1
    assert row["cart_count"] == 1
    assert row["purchase_count"] == 2
    assert row["revenue_proxy"] == pytest.approx(20.0)


def test_product_session_funnel_tracks_product_level_conversion() -> None:
    con = duckdb.connect()
    _create_raw_events_table(con)

    _insert_raw_events(
        con,
        [
            (
                "2019-10-01 00:00:00",
                "view",
                "1",
                "100",
                "electronics",
                "brand_a",
                "50.0",
                "1",
                "sess_product",
                "test.csv",
            ),
            (
                "2019-10-01 00:01:00",
                "cart",
                "1",
                "100",
                "electronics",
                "brand_a",
                "50.0",
                "1",
                "sess_product",
                "test.csv",
            ),
            (
                "2019-10-01 00:02:00",
                "purchase",
                "1",
                "100",
                "electronics",
                "brand_a",
                "50.0",
                "1",
                "sess_product",
                "test.csv",
            ),
            (
                "2019-10-01 00:03:00",
                "view",
                "2",
                "200",
                "accessories",
                None,  # type: ignore
                "10.0",
                "1",
                "sess_product",
                "test.csv",
            ),
        ],
    )

    build_events_clean(con)
    build_product_session_funnel(con)

    converted = _get_product_session_row(con, "sess_product", 1)
    not_converted = _get_product_session_row(con, "sess_product", 2)

    assert converted["has_view"] is True
    assert converted["has_cart_after_view"] is True
    assert converted["has_purchase_after_cart"] is True
    assert converted["revenue_proxy"] == pytest.approx(50.0)
    assert converted["price_band"] == "50-100"

    assert not_converted["has_view"] is True
    assert not_converted["has_cart_after_view"] is False
    assert not_converted["has_purchase_after_cart"] is False
    assert not_converted["brand"] == "unknown"
