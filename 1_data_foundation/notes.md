Unique identifiers of each table-row
customers: customer_id
locations: geolocation_zip_code_prefix (only after cleaning; the raw table repeats each zip many times)
order items: order_id + order_item_id
Payments: order_id + payment_sequential
Reviews:	review_id + order_id
Order: order_id
Products: product_id
Sellers: seller_id
Category name: product_category_name



## Integrity table

| Parent → Child | Key | Cardinality | Child w/o parent | Parent w/o child | Safe to join? | Action |
|---|---|---|---|---|---|---|
| customers → orders | customer_id | 1:1 | 0 | 0 | Yes | Use customer_unique_id to count real people |
| orders → order_items | order_id | 1:N | 0 | 775 | Yes with care | Aggregate items per order before joining at order level; flag 8 non-canceled orders with no items |
| orders → payments | order_id | 1:N | 0 | 1 | Yes with care | Aggregate payments per order first; flag 1 delivered order with no payment |
| orders → reviews | order_id | N:N | 0 | 768 | No | review_id repeats across orders and some orders have several reviews; keep one review per order (latest) before joining |
| products → order_items | product_id | 1:N | 0 | 0 | Yes | — |
| sellers → order_items | seller_id | 1:N | 0 | 0 | Yes | — |
| geolocation → customers | zip_code_prefix | N:N | 278 | 4,178 | No | Zip repeats ~1M times in geolocation; drop points outside Brazil, then aggregate to one row per zip (median lat/lng); 279 customers get no coordinates after cleaning |
| geolocation → sellers | zip_code_prefix | N:N | 7 | 16,776 | No | Same as above; 7 sellers get no coordinates |
| category → products | product_category_name | 1:N | 13 | 0 | Yes | Add 2 missing translations; fill 610 missing categories with "unknown" |


Data Cleaning : 

Customers Table:
customer_unique_id duplicates are normal. Olist creates a new customer_id for every order, and customer_unique_id is the actual person. 

Locations: 
Drop points outside Brazil (they're typos in the coordinates), then keep one row per zip with the median lat/lng.
- Flag: City names are spelled several ways. 
- Flag: zip 83252 only has a point in Spain, so that 1 customer loses its coordinates (278 → 279).

Order Items: 
order_id duplicates are normal. One row is one item in an order, and 9,803 orders have more than one item. The pair (order_id, order_item_id) is unique. 
The order_item_id outliers don't mean anything. 
- Flag: price and freight_value outliers are real. They're expensive items in a skewed column.
- Flag: 383 rows have freight_value = 0. That's plausibly free shipping, not an error.

Payments: 
order_id duplicates are normal. One row is one payment, and 2,961 orders were split across several. 
- Flag: 9 payments of 0, 2 with 0 installments, 3 with payment_type = not_defined, and 1 order with no payment row.

Reviews: 
review_id duplicates are normal here. Missing titles and messages are expected. The text is optional: 88% have no title and 57% have neither title nor message

Orders: 
The missing dates follow order_status. A canceled, unavailable or still-processing order never got shipped or delivered, so of course those dates are empty.
- Flag: 8 orders are marked delivered but have no delivery date.
14 delivered orders have no order_approved_at.
166 orders were handed to the carrier before they were purchased.
23 orders were delivered before the carrier picked them up.

Products: 
Outliers: 
The largest dimension is 105–118 cm and the heaviest item is 40 kg. The size limits look like shipping-carrier limits, and these are real large items like furniture (keep them)
- flag: 4 products weigh 0 g. That's a data error; set it to missing. (not done in the code yet)
610 products have no category, and the same 610 also have no name length, description length or photo count. Fill the category with "unknown" rather than dropping them, because they still appear in orders.
- flag: Column names are misspelled: product_name_lenght and product_description_lenght. 



More Flags (payments): 
Vouchers: 3,866 orders used a voucher, but in only 3,191 of them was the voucher the main payment type. In the other 675 it topped up a card or boleto payment.
Zero installments: 2 orders have a credit card payment with 0 installments. Looks like a data-entry error.
not_defined type: 3 orders have not_defined as their payment type, and all 3 paid 0.00.
Many payments on one order: one order has 29 separate payments, all vouchers.
The 1 order with no payment is delivered, with 3 items worth 143.46. The payment record looks lost.


Step 1: Clean the lookup tables (data_prep.py)

Fix translations, products and locations, then save every table to data/data_prep.


Step 2: Enrich the items table (items_join)

What: start from order_items (one row per item), then add information to each item:

join products on product_id → category
join sellers on seller_id → seller city, state and zip
join the clean geolocation on the seller’s zip → seller coordinates

Check: the row count is exactly the same as order_items. Every table joined has one row per key, so nothing can multiply. If the count goes up, one of the lookup tables isn't unique, so go back to step 1.

Why at item level: products and sellers belong to items, not to orders. One order can contain a phone from seller A and a case from seller B. If you aggregate to order level first, you can no longer tell which product came from which seller.

Empty cells: text columns are filled with "unknown". Numbers (like coordinates) stay empty, because "unknown" would turn them into text. 253 items have no seller coordinates.


Step 3: Reduce the child tables to one row per order

3a. Items → items_agg
Group by order_id and calculate:

number of items, distinct products and distinct sellers
total price, total freight, and order value (price + freight)
main category and main seller: sort each order's items by price, highest first, and keep the first row's category and seller (with that seller's state and coordinates). If two items cost the same, the lower order_item_id wins.

Check: row count = orders − 775 (no items). 

3b. Payments → payment_agg

total paid, number of payments, number of payment types
main payment type (the type with the largest amount). If two types have the same amount, the alphabetical first wins.
maximum number of installments, and whether a voucher was used

Check: row count = orders − 1.

3c. Reviews → review_agg

Sort each order's reviews by date, newest first, and keep the first.
Keep the score, whether there's a comment, and the review date.

Check: row count = orders − 768.

Why: this is the fan-out rule from the integrity table. Each of these tables has several rows per order, so they must be reduced before they touch the orders table. 
Judgement calls: 
- The most expensive item defines the category and seller.
- The latest review counts.
- Same-day ties: review_creation_date has no time of day, so the later review_answer_timestamp wins.
- What counts as a comment: only review_comment_message. A review with only a title has no comment.


Step 4: Add coordinates to customers (customer_location_join)

Join customers to the clean geolocation on the customer's zip → customer coordinates.
Check: row count unchanged, 279 customers without coordinates.
Why separately: customer_id is 1:1 with orders, so it needs no reducing, only enriching.


Step 5: Assemble the table (integrity_table)

Start with orders. It's the base: it decides what one row represents (one order). Then left-join customers, items_agg, payment_agg and review_agg. 
Result: 99,441 rows, 38 columns.

Flags: has_items, has_payment, has_review, has_customer_coords. False = that join found nothing, so the columns from it are empty.


Step 6: Final checks (final_checks)

- Row count = 99,441 and order_id is unique.
- Flag counts: 775 without items, 1 without payment, 768 without review, 279 without coordinates.
- Money: total_paid vs order_value. 303 of 98,665 orders differ by more than 1 cent:
  249 paid more in installments (probably interest), 15 paid more with 1 installment, 39 paid less.
- Saved to data/processed/orders_enriched.csv (CSV, because pyarrow isn't installed. Dates and True/False come back as text).
