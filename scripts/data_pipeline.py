import duckdb
import polars as pl
import logging

# Set up basic logging for our pipeline
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def process_funnel_data(input_path: str, output_path: str):
    logging.info(f"Starting data processing for {input_path}")

    # 1. DuckDB streams the CSV and aggregates at the brand/category level
    # We count DISTINCT users to measure true conversion, not just raw clicks
    query = f"""
        SELECT 
            category_code,
            brand,
            COUNT(DISTINCT CASE WHEN event_type = 'view' THEN user_id END) AS unique_views,
            COUNT(DISTINCT CASE WHEN event_type = 'cart' THEN user_id END) AS unique_carts,
            COUNT(DISTINCT CASE WHEN event_type = 'purchase' THEN user_id END) AS unique_purchases
        FROM read_csv_auto('{input_path}', ignore_errors=true)
        WHERE category_code IS NOT NULL 
          AND brand IS NOT NULL
        GROUP BY 1, 2
        HAVING unique_views > 50 -- Filter out noise from low-traffic products
    """

    # 2. Execute SQL and instantly convert to a Polars DataFrame (.pl())
    logging.info("Executing DuckDB query and converting to Polars...")
    df_funnel = duckdb.query(query).pl()

    # 3. Use Polars to add business logic (Conversion Rates)
    logging.info("Calculating conversion metrics...")

    # issue: Account for "Buy It Now" by ensuring carts >= purchases
    # the pytest was failing the first assertion of there not being more purchases than carts, with the first time running it having
    # 1618 instances of purchases exceeding the number of carts, by the Buy It Now button, which bypasses the cart event
    # so to fix this, the business logic is adjusted: if a user purchased an item, then it is assumed that it was passed in the cart
    df_funnel = df_funnel.with_columns(
        pl.max_horizontal("unique_carts", "unique_purchases").alias("adjusted_carts")
    )

    df_funnel = df_funnel.with_columns(
        [
            (pl.col("adjusted_carts") / pl.col("unique_views")).alias(
                "view_to_cart_rate"
            ),
            (pl.col("unique_purchases") / pl.col("adjusted_carts")).alias(
                "cart_to_purchase_rate"
            ),
            (pl.col("unique_purchases") / pl.col("unique_views")).alias(
                "overall_conversion_rate"
            ),
        ]
    ).fill_nan(
        0
    )  # Handle division by zero if carts = 0

    # 4. Save as Parquet for further analysis
    df_funnel.write_parquet(output_path)
    logging.info(f"Pipeline complete. Aggregated data saved to {output_path}")


if __name__ == "__main__":
    process_funnel_data(
        input_path="data/raw/2019-Oct.csv",
        output_path="data/processed/funnel_aggregates.parquet",
    )
