import pandas as pd
from pathlib import Path


PREP_PATH = Path(__file__).resolve().parent.parent / "data" / "data_prep"
PROCESSED_PATH = Path(__file__).resolve().parent.parent / "data" / "processed"


def print_shape(step, table):
    """Print the rows x columns of the table after a step, so a change in shape is easy to spot."""
    print(f"{step:<40} rows: {table.shape[0]:>8,}   columns: {table.shape[1]:>3}")


def join_table(left, right, on, step, how="left"):
    """Join right onto left and print the shape before and after.

    The integrity table has one row per order item, so a lookup join must keep the row count.
    If the rows change, the right table has duplicate keys and the merge multiplied rows.
    """
    rows_before = len(left)
    merged = left.merge(right, on=on, how=how)
    print_shape(step, merged)
    if len(merged) != rows_before:
        print(f"  WARNING: rows changed from {rows_before:,} to {len(merged):,}")
    return merged


def fill_missing(table):
    """Print the number of empty cells per column, then fill the empty text cells with "unknown".

    Numeric columns (prices, coordinates) are left empty: "unknown" would turn them into text
    and break any math or mapping on them.
    """
    print("\nEmpty cells per column:")
    print(table.isna().sum().to_string())
    table = table.copy()
    text_columns = table.select_dtypes(exclude="number").columns
    table[text_columns] = table[text_columns].fillna("unknown")
    return table


def items_join():
    """Enrich the order items with product category, seller location and seller coordinates."""
    items = pd.read_csv(PREP_PATH / "order_items.csv")
    print_shape("order items (start)", items)

    products = pd.read_csv(PREP_PATH / "products.csv", usecols=["product_id", "product_category_name"])
    items = join_table(items, products, "product_id", "+ products (category)")

    sellers = pd.read_csv(PREP_PATH / "sellers.csv")
    items = join_table(items, sellers, "seller_id", "+ sellers (city, state, zip)")

    # the clean locations table has one row per zip; rename its columns so they read as the seller's
    seller_locations = pd.read_csv(PREP_PATH / "locations.csv").rename(columns={
        "geolocation_zip_code_prefix": "seller_zip_code_prefix",
        "geolocation_lat": "seller_lat",
        "geolocation_lng": "seller_lng",
    })
    items = join_table(items, seller_locations, "seller_zip_code_prefix", "+ locations (seller coordinates)")
    print(f"  items whose seller zip has no coordinates: {items['seller_lat'].isna().sum():,}")

    items = fill_missing(items)
    print_shape("after filling missing", items)
    return items


def items_agg(items):
    """Aggregate the item rows to one row per order.

    - counts: items, distinct products, distinct sellers
    - money: total price, total freight, order value (price + freight)
    - main item: the most expensive item in the order gives the main category and main seller
      (with that seller's state and coordinates); ties go to the lowest order_item_id
    """
    print()
    print_shape("items (before aggregation)", items)

    totals = items.groupby("order_id").agg(
        n_items=("order_item_id", "count"),
        n_products=("product_id", "nunique"),
        n_sellers=("seller_id", "nunique"),
        total_price=("price", "sum"),
        total_freight=("freight_value", "sum"),
    )
    totals["order_value"] = totals["total_price"] + totals["total_freight"]

    main_item = (
        items.sort_values(["order_id", "price", "order_item_id"], ascending=[True, False, True])
        .drop_duplicates("order_id")
        .set_index("order_id")
        [["product_category_name", "seller_id", "seller_state", "seller_lat", "seller_lng"]]
        .rename(columns={
            "product_category_name": "main_category",
            "seller_id": "main_seller_id",
            "seller_state": "main_seller_state",
            "seller_lat": "main_seller_lat",
            "seller_lng": "main_seller_lng",
        })
    )

    orders = totals.join(main_item).reset_index()
    print_shape("items_agg (one row per order)", orders)
    return orders


# orders with no row in the items table (found in the orphan check in data_prep.py)
ORDERS_WITHOUT_ITEMS = 775


def check_items_agg(items_by_order):
    """Check that items_agg has one row per order: every order except the 775 with no items."""
    orders = pd.read_csv(PREP_PATH / "orders.csv", usecols=["order_id"])
    expected = len(orders) - ORDERS_WITHOUT_ITEMS
    unique_orders = items_by_order["order_id"].is_unique
    passed = unique_orders and len(items_by_order) == expected
    print(f"\nCheck items_agg: {len(items_by_order):,} rows, expected {len(orders):,} orders "
          f"- {ORDERS_WITHOUT_ITEMS} without items = {expected:,}; order_id unique: {unique_orders}")
    print("  PASS" if passed else "  FAIL")
    return passed


def payment_agg():
    """Aggregate the payment rows to one row per order.

    - totals: total paid, number of payments, number of payment types
    - main payment type: the type with the largest summed amount in the order
      (ties go to the type name that comes first alphabetically)
    - max installments, and whether a voucher was used
    """
    payments = pd.read_csv(PREP_PATH / "payments.csv")
    print()
    print_shape("payments (before aggregation)", payments)

    totals = payments.groupby("order_id").agg(
        total_paid=("payment_value", "sum"),
        n_payments=("payment_sequential", "count"),
        n_payment_types=("payment_type", "nunique"),
        max_installments=("payment_installments", "max"),
    )
    totals["used_voucher"] = payments.groupby("order_id")["payment_type"].apply(lambda types: (types == "voucher").any())

    main_type = (
        payments.groupby(["order_id", "payment_type"], as_index=False)["payment_value"].sum()
        .sort_values(["order_id", "payment_value", "payment_type"], ascending=[True, False, True])
        .drop_duplicates("order_id")
        .set_index("order_id")["payment_type"]
        .rename("main_payment_type")
    )

    payments_by_order = totals.join(main_type).reset_index()
    print_shape("payment_agg (one row per order)", payments_by_order)
    return payments_by_order


def payment_investigation(payments_by_order):
    """Print the payment oddities to look into: vouchers as top-ups, 0 installments, not_defined types, many payments."""
    payments = pd.read_csv(PREP_PATH / "payments.csv")
    print("\n=== Payment investigation ===")

    voucher_orders = payments_by_order["used_voucher"].sum()
    voucher_main = (payments_by_order["main_payment_type"] == "voucher").sum()
    print(f"Vouchers: {voucher_orders:,} orders used a voucher; it was the main payment type in {voucher_main:,}, "
          f"and topped up another payment in the other {voucher_orders - voucher_main:,}")

    zero_installments = payments[payments["payment_installments"] == 0]
    print(f"\nZero installments: {zero_installments['order_id'].nunique():,} orders "
          f"({len(zero_installments):,} payment rows) have 0 installments")
    print(zero_installments.to_string(index=False))

    not_defined = payments[payments["payment_type"] == "not_defined"]
    print(f"\nnot_defined type: {not_defined['order_id'].nunique():,} orders have a not_defined payment")
    print(not_defined.to_string(index=False))

    most_payments = payments_by_order.loc[payments_by_order["n_payments"].idxmax()]
    print(f"\nMany payments: order {most_payments['order_id']} has {most_payments['n_payments']} payments")
    print(payments[payments["order_id"] == most_payments["order_id"]]["payment_type"].value_counts().to_string())
    print("Orders by number of payments:")
    print(payments_by_order["n_payments"].value_counts().sort_index().to_string())


def review_agg():
    """Reduce the reviews to one row per order: the newest review counts.

    Reviews are sorted by creation date, newest first; the creation date has no time of day,
    so ties on the same day go to the latest answer timestamp.
    Keeps the score, whether the review has a comment message, and the review date.
    """
    reviews = pd.read_csv(PREP_PATH / "reviews.csv")
    print()
    print_shape("reviews (before aggregation)", reviews)

    reviews_by_order = (
        reviews.sort_values(["order_id", "review_creation_date", "review_answer_timestamp"],
                            ascending=[True, False, False])
        .drop_duplicates("order_id")
        .assign(has_comment=lambda r: r["review_comment_message"].notna())
        [["order_id", "review_score", "has_comment", "review_creation_date"]]
        .reset_index(drop=True)
    )
    print_shape("review_agg (one row per order)", reviews_by_order)
    return reviews_by_order


# orders with no review (found in the orphan check in data_prep.py)
ORDERS_WITHOUT_REVIEWS = 768


def check_review_agg(reviews_by_order):
    """Check that review_agg has one row per order: every order except the 768 with no review."""
    orders = pd.read_csv(PREP_PATH / "orders.csv", usecols=["order_id"])
    expected = len(orders) - ORDERS_WITHOUT_REVIEWS
    unique_orders = reviews_by_order["order_id"].is_unique
    passed = unique_orders and len(reviews_by_order) == expected
    print(f"\nCheck review_agg: {len(reviews_by_order):,} rows, expected {len(orders):,} orders "
          f"- {ORDERS_WITHOUT_REVIEWS} without reviews = {expected:,}; order_id unique: {unique_orders}")
    print("  PASS" if passed else "  FAIL")
    return passed


def customer_location_join():
    """Add coordinates to customers by joining the clean locations on the customer's zip prefix.

    customer_id is 1:1 with orders, so customers needs no reducing, only enriching.
    """
    customers = pd.read_csv(PREP_PATH / "customers.csv")
    print()
    print_shape("customers (start)", customers)

    # the clean locations table has one row per zip; rename its columns so they read as the customer's
    customer_locations = pd.read_csv(PREP_PATH / "locations.csv").rename(columns={
        "geolocation_zip_code_prefix": "customer_zip_code_prefix",
        "geolocation_lat": "customer_lat",
        "geolocation_lng": "customer_lng",
    })
    customers = join_table(customers, customer_locations, "customer_zip_code_prefix", "+ locations (customer coordinates)")
    return customers


# customers whose zip has no coordinates in the clean locations table:
# 278 customers whose zip is missing from the raw geolocation data, plus 1 customer with zip 83252,
# whose only point (lat 42.18, lng -8.72, in Spain) fix_locations drops as outside Brazil
CUSTOMERS_WITHOUT_COORDINATES = 279


def check_customer_location_join(customers):
    """Check that the join kept one row per customer and that 279 customers have no coordinates."""
    rows_before = len(pd.read_csv(PREP_PATH / "customers.csv", usecols=["customer_id"]))
    without_coordinates = customers["customer_lat"].isna().sum()
    passed = len(customers) == rows_before and without_coordinates == CUSTOMERS_WITHOUT_COORDINATES
    print(f"\nCheck customer_location_join: {len(customers):,} rows, expected {rows_before:,}; "
          f"{without_coordinates:,} without coordinates, expected {CUSTOMERS_WITHOUT_COORDINATES}")
    print("  PASS" if passed else "  FAIL")
    return passed


def integrity_table_flags(table):
    """Add True/False flags for which joins found a match, so incomplete orders are easy to filter."""
    table = table.copy()
    table["has_items"] = table["n_items"].notna()
    table["has_payment"] = table["total_paid"].notna()
    table["has_review"] = table["review_score"].notna()
    table["has_customer_coords"] = table["customer_lat"].notna()

    flags = ["has_items", "has_payment", "has_review", "has_customer_coords"]
    print("\nOrders without a match per flag:")
    print((~table[flags]).sum().to_string())
    print_shape("+ flags", table)
    return table


TOTAL_ORDERS = 99_441
ORDERS_WITHOUT_PAYMENT = 1
# order_value and total_paid are sums of floats, so differences below a cent are rounding
MONEY_TOLERANCE = 0.01


def money_reconciliation(table):
    """Compare total_paid with order_value for orders that have both, and group the mismatches by likely cause.

    - paid more, in installments: the customer paid interest on an installment plan
    - paid more, 1 installment: extra charge with no installment to explain it
    - paid less: discount or partial payment not recorded as a voucher
    """
    both = table[table["has_items"] & table["has_payment"]]
    difference = (both["total_paid"] - both["order_value"]).round(2)
    mismatched = both[difference.abs() > MONEY_TOLERANCE].assign(difference=difference)

    paid_more = mismatched["difference"] > 0
    in_installments = mismatched["max_installments"] > 1
    causes = pd.Series({
        "paid more, in installments (interest)": (paid_more & in_installments).sum(),
        "paid more, 1 installment": (paid_more & ~in_installments).sum(),
        "paid less": (~paid_more).sum(),
    })
    print(f"\nMoney reconciliation: {len(mismatched):,} of {len(both):,} orders with items and payment "
          f"differ by more than {MONEY_TOLERANCE}")
    print(causes.to_string())
    print(f"  differences range from {mismatched['difference'].min():,.2f} to {mismatched['difference'].max():,.2f}, "
          f"median {mismatched['difference'].median():,.2f}")
    return mismatched


def final_checks(table):
    """Run the final tests on the integrity table, reconcile the money, and save it to data/processed."""
    print("\n=== Final checks ===")
    expected_missing = {
        "has_items": ORDERS_WITHOUT_ITEMS,
        "has_payment": ORDERS_WITHOUT_PAYMENT,
        "has_review": ORDERS_WITHOUT_REVIEWS,
        "has_customer_coords": CUSTOMERS_WITHOUT_COORDINATES,
    }
    checks = {
        f"row count = {TOTAL_ORDERS:,}": len(table) == TOTAL_ORDERS,
        "order_id is unique": table["order_id"].is_unique,
    }
    for flag, expected in expected_missing.items():
        actual = (~table[flag]).sum()
        checks[f"{flag} False: {actual:,}, expected {expected:,}"] = actual == expected
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")

    money_reconciliation(table)

    PROCESSED_PATH.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_PATH / "orders_enriched.csv"
    table.to_csv(path, index=False)
    print(f"\nSaved the integrity table to {path}")
    return all(checks.values())


def integrity_table():
    """Build the integrity table for the EDA: one row per order.

    Orders is the base and decides what one row represents. Every other table is first reduced
    (items, payments, reviews) or enriched (customers) to one row per order, then left-joined,
    so no join can change the row count.
    """
    items = items_join()
    items_by_order = items_agg(items)
    check_items_agg(items_by_order)
    payments_by_order = payment_agg()
    payment_investigation(payments_by_order)
    reviews_by_order = review_agg()
    check_review_agg(reviews_by_order)
    customers = customer_location_join()
    check_customer_location_join(customers)

    print("\n=== Assemble the integrity table ===")
    table = pd.read_csv(PREP_PATH / "orders.csv")
    print_shape("orders (start)", table)
    table = join_table(table, customers, "customer_id", "+ customers")
    table = join_table(table, items_by_order, "order_id", "+ items_agg")
    table = join_table(table, payments_by_order, "order_id", "+ payment_agg")
    table = join_table(table, reviews_by_order, "order_id", "+ review_agg")

    print("\nEmpty cells per column:")
    missing = table.isna().sum()
    print(missing[missing > 0].to_string())

    table = integrity_table_flags(table)
    return table


if __name__ == "__main__":
    table = integrity_table()
    final_checks(table)
