import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


print("Data Preparation Script Started Successfully")
DATA_PATH = Path(__file__).resolve().parent.parent / "data"
PLOTS_PATH = Path(__file__).resolve().parent / "variable_dist"

BAR_COLOR = "#2a78d6"
SURFACE_COLOR = "#fcfcfb"
TEXT_COLOR = "#52514e"
plt.rcParams.update({
    "figure.facecolor": SURFACE_COLOR,
    "axes.facecolor": SURFACE_COLOR,
    "axes.edgecolor": TEXT_COLOR,
    "axes.labelcolor": TEXT_COLOR,
    "axes.titlecolor": "#0b0b0b",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "axes.axisbelow": True,
    "grid.color": "#e5e4e0",
    "xtick.color": TEXT_COLOR,
    "ytick.color": TEXT_COLOR,
})
t_customers = pd.read_csv(DATA_PATH/ "olist_customers_dataset.csv")
t_geolocation = pd.read_csv(DATA_PATH/ "olist_geolocation_dataset.csv")
t_order_items = pd.read_csv(DATA_PATH/ "olist_order_items_dataset.csv")
t_order_payments = pd.read_csv(DATA_PATH/ "olist_order_payments_dataset.csv")
t_order_reviews = pd.read_csv(DATA_PATH/ "olist_order_reviews_dataset.csv")
t_orders = pd.read_csv(DATA_PATH/ "olist_orders_dataset.csv")
t_products = pd.read_csv(DATA_PATH/ "olist_products_dataset.csv")
t_sellers = pd.read_csv(DATA_PATH/ "olist_sellers_dataset.csv")
t_category_name_translation = pd.read_csv(DATA_PATH/"product_category_name_translation.csv")

tables = {
            "customers": t_customers,
            "Locations":t_geolocation,
            "Order times": t_order_items,
            "Payments" : t_order_payments, 
            "Reviews":t_order_reviews,
            "Orders": t_orders,
            "Products" : t_products, 
            "Sellers" : t_sellers, 
            "Category Name": t_category_name_translation
          }

def summarize_tables(tables):
    """Return one summary row (shape, missing values, duplicates, memory) per table."""
    summary_rows = []
    for name, table in tables.items():
        summary_rows.append({
            "table": name,
            "rows": table.shape[0],
            "columns": table.shape[1],
            "missing_values": table.isna().sum().sum(),
            "duplicate_rows": table.duplicated().sum(),
            "memory_mb": round(table.memory_usage(deep=True).sum() / 1024**2, 1),
        })
    return pd.DataFrame(summary_rows).set_index("table")

def describe_distribution(column, table_name):
    """Save a chart of how the values in one column are spread and return the image path.

    - few distinct values (<= 20): bar chart of counts per value
    - numbers: density histogram
    - dates: histogram of counts over time
    - many distinct text values (IDs, cities): count of each value, ranked from most to least common
    """
    values = column.dropna()
    if values.empty:
        return "all missing"

    fig, ax = plt.subplots(figsize=(8, 4.5))
    is_numeric = pd.api.types.is_numeric_dtype(values)
    dates = None if is_numeric else pd.to_datetime(values, format="ISO8601", errors="coerce")
    subtitle = f"{len(values):,} values, {values.nunique():,} distinct, {column.isna().sum():,} missing"

    if values.nunique() <= 20:
        counts = values.value_counts()
        counts = counts.sort_index() if is_numeric else counts.sort_values()
        ax.barh(counts.index.astype(str), counts.values, color=BAR_COLOR, height=0.7)
        ax.set_xlabel("count")
        ax.grid(axis="y", visible=False)
    elif is_numeric:
        # a few extreme values squash the rest of the histogram, so cut the x-axis at the 99th percentile
        cutoff = values.quantile(0.99)
        above_cutoff = (values > cutoff).sum()
        if above_cutoff:
            subtitle += f"; x-axis cut at 99th percentile ({cutoff:,.2f}), {above_cutoff:,} values above not shown"
            values = values[values <= cutoff]
        ax.hist(values, bins=50, density=True, color=BAR_COLOR, edgecolor=SURFACE_COLOR, linewidth=1)
        ax.set_xlabel(column.name)
        ax.set_ylabel("density")
        ax.grid(axis="x", visible=False)
    elif dates.notna().mean() > 0.95:
        ax.hist(dates.dropna(), bins=50, color=BAR_COLOR, edgecolor=SURFACE_COLOR, linewidth=1)
        ax.set_xlabel(column.name)
        ax.set_ylabel("count")
        ax.grid(axis="x", visible=False)
        fig.autofmt_xdate()
    else:
        counts = values.value_counts().to_numpy()
        ax.plot(np.arange(1, len(counts) + 1), counts, color=BAR_COLOR, linewidth=2)
        ax.set_ylim(bottom=0)
        ax.set_xlabel("distinct values, ranked from most to least common")
        ax.set_ylabel("times each value appears")

    ax.set_title(f"{table_name}: {column.name}", loc="left", fontsize=12, pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_COLOR, va="bottom")

    table_folder = PLOTS_PATH / table_name.lower().replace(" ", "_")
    table_folder.mkdir(parents=True, exist_ok=True)
    image_path = table_folder / f"{column.name}.png"
    fig.savefig(image_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return str(image_path.relative_to(PLOTS_PATH.parent))


SKIP_OUTLIER_WORDS = {"id", "zip", "code"}
# numeric columns where outliers still mean nothing: a 1-5 score, a counter, and coordinates
SKIP_OUTLIER_COLUMNS = {"review_score", "payment_sequential", "geolocation_lat", "geolocation_lng"}


def should_check_outliers(column):
    """Return False for columns where outliers mean nothing: IDs, zip codes / codes, text, and SKIP_OUTLIER_COLUMNS.

    The name is split on "_" so only whole words match (product_width_cm contains "id" but is not an ID).
    """
    if column.name in SKIP_OUTLIER_COLUMNS:
        return False
    name_words = set(str(column.name).lower().split("_"))
    if name_words & SKIP_OUTLIER_WORDS:
        return False
    return pd.api.types.is_numeric_dtype(column)


def count_outliers(column):
    """Count outliers with two methods: outside 1.5 * IQR, and more than 3 std from the mean (z-score)."""
    q1, q3 = column.quantile([0.25, 0.75])
    iqr = q3 - q1
    iqr_outliers = ((column < q1 - 1.5 * iqr) | (column > q3 + 1.5 * iqr)).sum()

    std = column.std()
    if std == 0 or pd.isna(std):
        zscore_outliers = 0
    else:
        z_scores = (column - column.mean()) / std
        zscore_outliers = (z_scores.abs() > 3).sum()

    return {"outliers_iqr": iqr_outliers, "outliers_zscore": zscore_outliers}


def summarize_single_table(tables):
    """Return a summary of single table column (missing values, data type, duplicates, outliers)"""
    profiles = {}
    for name, table in tables.items():
        summary_rows = []
        for column_name in table.columns:
            column = table[column_name]
            if should_check_outliers(column):
                outliers = count_outliers(column)
            else:
                outliers = {"outliers_iqr": None, "outliers_zscore": None}
            summary_rows.append({
                "column": column_name,
                "dtype": str(column.dtype),
                "missing": column.isna().sum(),
                "missing_pct": round(column.isna().mean() * 100, 1),
                "unique": column.nunique(),
                "duplicates": column.dropna().duplicated().sum(),
                **outliers
            })
        profiles[name] = pd.DataFrame(summary_rows).set_index("column")
    return profiles


def check_unique_keys(tables, candidate_keys):
    """Test whether each candidate key really identifies one row per table.

    candidate_keys is a list of (table name, key) pairs; a key is one column name or a list of columns,
    so the same table can be tested with several candidates. A valid key has 0 duplicates and 0 missing.
    """
    rows = []
    for table_name, key in candidate_keys:
        key_columns = [key] if isinstance(key, str) else list(key)
        table = tables[table_name]
        duplicates = table.duplicated(subset=key_columns).sum()
        missing = table[key_columns].isna().any(axis=1).sum()
        rows.append({
            "table": table_name,
            "key": " + ".join(key_columns),
            "rows": len(table),
            "unique": len(table) - duplicates,
            "duplicates": duplicates,
            "missing": missing,
            "is_unique": duplicates == 0 and missing == 0,
        })
    return pd.DataFrame(rows).set_index(["table", "key"])


def check_orphans(tables, relationships):
    """Check each parent-child link both ways and count the orphans.

    relationships is a list of (parent table, parent column, child table, child column).
    - child_without_parent: child rows whose key is not in the parent (usually a data error)
    - parent_without_child: distinct parent keys that no child row uses (often legitimate)
    Child rows with a missing key are counted separately in child_missing_key, not as orphans.
    """
    rows = []
    for parent_name, parent_column, child_name, child_column in relationships:
        parent_keys = tables[parent_name][parent_column].dropna()
        child_keys = tables[child_name][child_column]
        child_present = child_keys.dropna()
        rows.append({
            "parent": f"{parent_name}.{parent_column}",
            "child": f"{child_name}.{child_column}",
            "parent_keys": parent_keys.nunique(),
            "child_rows": len(child_keys),
            "child_missing_key": child_keys.isna().sum(),
            "child_without_parent": (~child_present.isin(parent_keys)).sum(),
            "parent_without_child": parent_keys[~parent_keys.isin(child_present)].nunique(),
        })
    return pd.DataFrame(rows).set_index(["parent", "child"])


summary = summarize_tables(tables)
print(summary.to_string())

profiles = summarize_single_table(tables)
for name, profile in profiles.items():
    print(f"\n=== {name} ===")
    print(profile.to_string())

candidate_keys = [
    ("customers", "customer_id"),
    ("Locations", "geolocation_zip_code_prefix"),
    ("Locations", ["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"]),
    ("Order times", ["order_id", "order_item_id"]),
    ("Payments", ["order_id", "payment_sequential"]),
    ("Reviews", ["review_id", "order_id"]),
    ("Orders", "order_id"),
    ("Products", "product_id"),
    ("Sellers", "seller_id"),
    ("Category Name", "product_category_name"),
]
print("\n=== Unique keys ===")
print(check_unique_keys(tables, candidate_keys).to_string())

relationships = [
    ("customers", "customer_id", "Orders", "customer_id"),
    ("Orders", "order_id", "Order times", "order_id"),
    ("Orders", "order_id", "Payments", "order_id"),
    ("Orders", "order_id", "Reviews", "order_id"),
    ("Products", "product_id", "Order times", "product_id"),
    ("Sellers", "seller_id", "Order times", "seller_id"),
    ("Locations", "geolocation_zip_code_prefix", "customers", "customer_zip_code_prefix"),
    ("Locations", "geolocation_zip_code_prefix", "Sellers", "seller_zip_code_prefix"),
    ("Category Name", "product_category_name", "Products", "product_category_name"),
]
print("\n=== Orphans ===")
print(check_orphans(tables, relationships).to_string())

for name, table in tables.items():
    for column_name in table.columns:
        describe_distribution(table[column_name], name)
print(f"\nDistribution charts saved to {PLOTS_PATH}")
