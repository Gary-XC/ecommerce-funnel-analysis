# Data Dictionary

## Raw Event Data

Source: Kaggle dataset, "E-commerce behavior data from multi-category store".

| Field | Type | Description | Analytical Use |
|---|---|---|---|
| `event_time` | timestamp | Time when event happened in UTC. | Session ordering, time-to-conversion, cohort dating. |
| `event_type` | string | Event type: `view`, `cart`, `remove_from_cart`, `purchase`. | Funnel stage construction. |
| `product_id` | integer/string | Unique product identifier. | Product-level funnel and repeat-view analysis. |
| `category_id` | integer | Product category ID. | Category grouping. |
| `category_code` | string | Product category taxonomy code, may be missing. | Category performance and metadata completeness analysis. |
| `brand` | string | Downcased brand name, may be missing. | Brand-level conversion and metadata completeness analysis. |
| `price` | float | Product price. | Price bands, revenue proxy, average order value proxy. |
| `user_id` | integer/string | Permanent user ID. | Repeat-user analysis, optional user-level funnel. |
| `user_session` | string | Temporary session ID. | Primary analytical unit for session funnel. |

## Event Types

| Event | Meaning | Funnel Role |
|---|---|---|
| `view` | User viewed a product. | Top of funnel. |
| `cart` | User added a product to cart. | Consideration stage. |
| `remove_from_cart` | User removed a product from cart. | Friction / hesitation diagnostic. |
| `purchase` | User purchased a product. | Conversion event. |

## Session Notes

A session can contain multiple purchase events. According to the dataset documentation, this is acceptable because it can represent a single order with multiple line items.

For this project:

- A session is considered a **viewed session** if it contains at least one `view`.
- A session is considered a **carted session** if it contains at least one `cart` after a `view`.
- A session is considered a **purchased session** if it contains at least one `purchase` after a qualifying cart event.
- Sessions with purchase but no prior cart are flagged as **direct purchase anomalies** for data-quality review.