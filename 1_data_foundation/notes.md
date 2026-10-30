Unique identifiers of each table-row
customers: customer_id
locations: customer_id + zip_code_prefix
order items: order_id + product_id 
Payments: order_id + payment_sequential
Reviews:	review_id + order_id
Order: order_id
Products: product_id
Sellers: seller_id
Category name: product_category_name



Integrity Table: 


## Integrity table

| Parent → Child | Key | Cardinality | Child w/o parent | Parent w/o child | Safe to join? | Action |
|---|---|---|---|---|---|---|
| customers → orders | customer_id | 1:1 | 0 | 0 | Yes | Use customer_unique_id to count real people |
| orders → order_items | order_id | 1:N | 0 | 775 | Yes with care | Aggregate items per order before joining at order level; flag 8 non-canceled orders with no items |
| orders → payments | order_id | 1:N | 0 | 1 | Yes with care | Aggregate payments per order first; flag 1 delivered order with no payment |
| orders → reviews | order_id | N:N | 0 | 768 | No | review_id repeats across orders and some orders have several reviews; keep one review per order (latest) before joining |
| products → order_items | product_id | 1:N | 0 | 0 | Yes | — |
| sellers → order_items | seller_id | 1:N | 0 | 0 | Yes | — |
| geolocation → customers | zip_code_prefix | N:N | 278 | 4,178 | No | Zip repeats ~1M times in geolocation; aggregate to one row per zip (mean lat/lng) first; 278 customers get no coordinates |
| geolocation → sellers | zip_code_prefix | N:N | 7 | 16,776 | No | Same as above; 7 sellers get no coordinates |
| category → products | product_category_name | 1:N | 13 | 0 | Yes | Add 2 missing translations; fill 610 missing categories with "unknown" |


Data Cleaning : 

Customers Table:
customer_unique_id duplicates are normal. Olist creates a new customer_id for every order, and customer_unique_id is the actual person. 

Locations: 
Ignore outliers. 
- Flag: City Nmaes are spelled several ways. 

Orer Items: 
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
- flag: 4 products weigh 0 g. That's a data error; set it to missing.
610 products have no category, and the same 610 also have no name length, description length or photo count. Fill the category with "unknown" rather than dropping them, because they still appear in orders.
- flag: Column names are misspelled: product_name_lenght and product_description_lenght. 