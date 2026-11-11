# Business case: growth without retention at Olist

Plots referenced below are in `eda_plots/`. Code: `eda_analysis.py`.

## 1. Context

**What this is about.** Olist is a Brazilian online marketplace. Small sellers list their products and customers buy through the platform. The public Olist dataset covers about 99k orders in 9 linked tables: orders, items, payments, reviews, customers, sellers, products, categories and geolocation.

**The data I used.** After cleaning and joining the tables (see the integrity table in `notes.md`), I kept the orders that count as a sale: placed between Jan 2017 and Aug 2018, not canceled or unavailable, with at least one item. Months outside this window hold only a few hundred orders and would show up as fake drops.

| | |
|---|---|
| Sold orders | 97,905 |
| Unique customers | 94,703 |
| Sellers | 3,020 |
| Revenue (total paid, BRL) | 15.7M |
| Orders delivered | 98% |
| Customers in São Paulo state | 42% of orders |

**Why this matters.** This is the foundation for the rest of the project (KPIs, funnel, forecasting, churn). Before building models on top of it, I need to know what is actually driving revenue.

## 2. Problem definition

> Olist's revenue growth in 2017–18 came almost entirely from acquiring new customers. Only about 1.3% of them came back within 90 days, so revenue depends on constantly buying new customers.

Evidence in one line: between Jan–Aug 2017 and Jan–Aug 2018 revenue grew 140%, and 99% of that growth was more customers. Returning customers contributed 2.2% of revenue.

## 3. Research question

> How much of Olist's 2017–18 revenue growth came from new customers versus repeat purchases, and which first-order experiences and product categories make a customer more likely to come back? This is for a growth or CRM lead deciding between acquisition spend and retention.

| | |
|---|---|
| What | the new vs returning split of growth, and the drivers of repeat purchase |
| Why | to decide where the next unit of effort pays off |
| How | monthly new vs returning counts, a growth decomposition, a Black Friday test, and 90-day repeat rates by first-order experience and category |
| For whom | a growth or CRM lead at the marketplace |

**Method note.** A customer is identified by `customer_unique_id`. A return is an order on a later day than the first (same-day orders count as one session). The repeat rate is the share of first-time customers who return within 90 days. Only first-order months with a full 90-day window are used (Jan 2017 to May 2018, 76,556 customers). Every rate carries a 95% interval, because the numbers are small.

## 4. Key insights

### A. Growth was volume, and the volume was new customers
1. **Growth came from customer count.** Revenue grew +140% (Jan–Aug 2018 vs Jan–Aug 2017). Customers grew +139%. Orders per customer fell 0.6% and average order value rose 1.3%. So 99% of growth was more customers. (`growth_decomposition.png`)
2. **The base is almost all new.** Only 2.2% of 94,703 customers ordered again on a later day. In a typical month 98% of buyers are new. The returning share rises from 0% to about 2–3%, partly because the customer base was still building up. (`new_vs_returning_ratio_month.png`)
3. **Repeat is low and flat.** The 90-day repeat rate is 1.31% overall and ranges from 0.9% to 1.9% by cohort, with no upward trend. (`repeat_rate_90d_month.png`)
4. **Basket size is flat.** Average order value stays around 161 BRL (range 147–174). (`aov_month.png`)

### B. Black Friday 2017 was a spike, not a pull-forward
5. **The spike was huge.** 24 Nov 2017 had 1,166 orders and 178K BRL revenue, 7.5 times the average of the 3 Fridays before. AOV was lower (153 against 171), which points to discount-driven buying. (`black_friday_test.png`)
6. **It did not borrow from later.** Black Friday week ran +221% vs the 4-week baseline (487 vs 152 orders a day), adding about 2,350 extra orders. December stayed +20% above baseline, and the only weak stretch is the Christmas lull.
7. **A higher level followed.** Jan–Feb 2018 runs +57% above the pre-Black-Friday baseline. This is an association, not proof. There is only one Black Friday in the data and the business was already growing.

### C. Why customers don't come back
8. **Service quality matters, but modestly.** Customers with a late first delivery return at about 1.0–1.15%, against 1.3–1.4% for on-time. The gap is −0.27 points (95% interval −0.53 to −0.01). Late deliveries cluster in remote states, so this is not proof that lateness causes churn. (`repeat_by_delivery_delay.png`)
9. **Happy customers return more.** Repeat rises from about 1.0–1.1% at 1–3 stars to 1.2% at 4 stars and 1.45% at 5 stars. A bad first experience (late or low review) flattens the rate to about 1.0–1.1%. (`repeat_by_review_score.png`)
10. **Even the happiest customers rarely return.** The best group (on time, 4–5 stars) returns at only 1.39%. So bad service explains a small part of the gap. Most customers don't come back even when everything goes well.
11. **Category matters more than delivery.** Best: `fashion_bags_accessories` (2.26%) and `bed_bath_table` (2.00%). Worst: `cool_stuff` (0.56%) and `electronics` (0.78%). Only `bed_bath_table` (solid sample) and `cool_stuff` are clearly different from average. The second-worst place is a statistical tie with three other categories. (`repeat_by_category.png`)
12. **Furniture is not naturally one-off.** `furniture_decor` returns at 1.55%, above average.
13. **Popular is not the same as sticky.** The top category by units (`bed_bath_table`) is also one of the stickiest, but `computers_accessories` (5th by units) is in the bottom group. (`top_categories.png`)
14. **Things that did not matter.** State differences are not robust (SP, RJ, MG all about 1.2–1.4%), and freight share has no effect (all five groups 1.2–1.4%). (`repeat_by_state.png`, `repeat_by_freight_share.png`)

### D. What sells most
15. **Top 5 products by units:** one `furniture_decor` product (527 units), one `bed_bath_table` (487) and three `garden_tools` (484, 391, 388). Even the top product has only about 500 buyers, too few for a product-level repeat rate. (`top_products.png`)

## 5. Conclusion

Olist grew fast through 2017 and the growth was almost purely customer acquisition: more customers each month, at a steady basket of about 160 BRL. Black Friday 2017 was a huge spike that did not just pull sales forward, and the platform ran at a higher level afterwards. But only about 1.3% of customers came back within 90 days, and returning customers produced just 2% of revenue.

Service quality plays a small role. Late deliveries and bad reviews are linked to a lower repeat rate, but even on-time, well-reviewed first orders return at only about 1.4%. Category matters more: repeat is highest in home textiles and fashion accessories and lowest in gadget and electronics purchases.

For a growth lead, this means retention is the largest untapped lever, but a first-order fix alone will not close the gap. A retention program should start with the categories that already hold customers.

## 6. Limits and caveats

- Repeat rates are small (about 1%), so many segment differences are inside the margin of error. Only differences whose 95% intervals do not overlap are called out.
- Repeat is measured on one account per person, and a customer who returns under a different account is invisible.
- Late delivery and review score overlap, and late deliveries are more common in remote states, so none of the links to repeat are proven causes.
- Revenue is `total_paid`, which includes installment interest.
- One Black Friday, so no year-on-year comparison is possible.
- Product ids have no names in the dataset, so products are identified by category and the first 6 characters of the id.

## 7. Still to do

- A bubble chart of category popularity (units) against stickiness (repeat rate), sized by revenue.
- Control for state, category and freight together, to see whether late delivery still matters on its own.
- An external benchmark for a typical e-commerce repeat rate, with source, to say whether 1.3% is low.
