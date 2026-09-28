import polars as pl
import pytest


def test_funnel_logic():
    # Load the processed data
    df = pl.read_parquet("data/processed/funnel_aggregates.parquet")

    # Assert 1: We should never have more purchases than adjusted carts (Buy it now feature bypassing the cart feature)
    # so adjusted carts include purchases - assumption being that if it was bought, then it was placed in the cart
    # purchases should be a subset of carts
    invalid_funnels = df.filter(pl.col("unique_purchases") > pl.col("adjusted_carts"))

    assert (
        len(invalid_funnels) == 0
    ), f"Found {len(invalid_funnels)} rows where purchases > carts"

    # Assert 2: Conversion rates should logically be between 0 and 1
    assert df["overall_conversion_rate"].max() <= 1.0  # type: ignore
    assert df["overall_conversion_rate"].min() >= 0.0  # type: ignore
