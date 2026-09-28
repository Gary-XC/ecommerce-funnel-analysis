# Project Charter: E-commerce Browse-to-Buy Funnel Analysis

## Business Problem

The online store generates substantial product browsing activity, but purchase conversion appears inefficient. Leadership needs to identify whether the primary leakage occurs during product consideration, cart abandonment, or purchase completion, and determine which product categories, price bands, or behavioral signals deserve optimization first.

## Primary Analytical Question

Among user sessions that contain at least one product view, which funnel stage has the largest statistically meaningful drop-off: view-to-cart or cart-to-purchase?

## Secondary Questions

- Which categories have the weakest conversion performance?
- Do missing brand or category metadata reduce conversion?
- Are higher-priced products less likely to convert from cart to purchase?
- Do cart removals indicate fatal friction or recoverable hesitation?
- Do repeated product views predict purchase?
- How much incremental revenue could be recovered from a small conversion improvement?

## Hypotheses 
- id: H3
    statement: 
        Cart removals are associated with lower purchase conversion.
    status: not_testable_in_this_extract
    reason: 
        The cleaned dataset contains zero remove_from_cart events.

## North Star Metric

**Session Purchase Conversion Rate**

```text
Sessions with at least one purchase
------------------------------------
Sessions with at least one product view

Total purchase price proxy
--------------------------
Sessions with at least one product view

Product View -> Add to Cart -> Purchase

Remove From Cart


Primary Analytical Unit
user_session
Secondary Analytical Unit
user_session + product_id

Dataset:
Kaggle: E-commerce behavior data from multi-category store.

Event types:
view
cart
remove_from_cart
purchase
Key fields:
event_time
event_type
product_id
category_id
category_code
brand
price
user_id
user_session

Known Limitations:
No marketing channel data.
No device or geography data.
No checkout step granularity.
No returns, refunds, coupons, inventory, or shipping cost data.
Price is a product price proxy, not necessarily final paid amount.
Quantity is not available.
Only two months of behavior are observed.
User and session IDs are anonymized.

- `remove_from_cart` events are not present in this dataset extract, so cart-removal friction cannot be analyzed here.
- A material share of purchases occurs outside the strict view -> cart -> purchase path, likely representing direct purchase behavior, express checkout, or event-tracking gaps.
- The dataset does not document currency, so revenue figures are treated as monetary-unit proxies.
- The dataset does not include quantity, so purchase revenue is approximated by summing purchase event prices.