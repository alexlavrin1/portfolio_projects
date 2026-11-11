import pandas as pd
import numpy as np
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter


PROCESSED_PATH = Path(__file__).resolve().parent.parent / "data" / "processed"
PLOTS_PATH = Path(__file__).resolve().parent / "eda_plots"

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

DATE_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
    "review_creation_date",
]
# the CSV stores True/False as text; these two also have empty cells (no payment / no review)
BOOL_TEXT_COLUMNS = ["used_voucher", "has_comment"]


def load_orders():
    """Load orders_enriched.csv (one row per order) and restore the types the CSV lost.

    Dates are parsed back to datetime and the True/False text columns become nullable booleans,
    so an order without a payment or review keeps an empty cell instead of turning into False.
    """
    orders = pd.read_csv(
        PROCESSED_PATH / "orders_enriched.csv",
        parse_dates=DATE_COLUMNS,
        dtype={column: "string" for column in BOOL_TEXT_COLUMNS},
    )
    for column in BOOL_TEXT_COLUMNS:
        orders[column] = orders[column].map({"True": True, "False": False}).astype("boolean")
    return orders


def describe_columns(table):
    """Print the rows x columns of the table, then one line per column with its type."""
    print(f"Shape   rows: {table.shape[0]:,}   columns: {table.shape[1]}\n")
    width = max(len(column) for column in table.columns)
    print(f"{'column':<{width}}   type")
    for column, dtype in table.dtypes.items():
        print(f"{column:<{width}}   {dtype}")


def save_plot(fig, name, title, subtitle=""):
    """Add the title and subtitle in the shared style, save the figure to eda_plots/ and return its path."""
    ax = fig.axes[0]
    ax.set_title(title, loc="left", fontsize=12, pad=22)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=9, color=TEXT_COLOR, va="bottom")
    PLOTS_PATH.mkdir(parents=True, exist_ok=True)
    image_path = PLOTS_PATH / f"{name}.png"
    fig.savefig(image_path, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return image_path


# a second series takes the next categorical slot; text and axes stay in TEXT_COLOR
SERIES_COLORS = [BAR_COLOR, "#eb6834"]


def compact_number(value, _position=None):
    """Tick label in short form: 1,500 -> 1.5K, 2,000,000 -> 2M."""
    for limit, suffix in ((1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"{value / limit:.1f}".rstrip("0").rstrip(".") + suffix
    return f"{value:g}"


# months before 2017 and after August 2018 hold only a few hundred orders (mostly canceled at the end),
# so they would show up as fake drops at both ends of every trend line
SALES_START = "2017-01-01"
SALES_END = "2018-08-31"
# these never reached the customer, so they are not revenue
NOT_SOLD_STATUSES = ["canceled", "unavailable"]


def sold_orders(orders):
    """Keep the orders that count as a sale: inside the sales window, not canceled/unavailable, with items."""
    purchase_date = orders["order_purchase_timestamp"].dt.normalize()
    in_window = purchase_date.between(SALES_START, SALES_END)
    sold = orders[in_window & ~orders["order_status"].isin(NOT_SOLD_STATUSES) & orders["has_items"]].copy()
    print(f"Sold orders {SALES_START} to {SALES_END}: {len(sold):,} of {len(orders):,}")
    return sold


PERIODS = {"day": "D", "week": "W", "month": "M"}
PERIOD_TITLES = {"day": "Daily", "week": "Weekly", "month": "Monthly"}
METRIC_LABELS = {
    "orders": "orders", "items": "items ordered", "revenue": "revenue (BRL)", "aov": "AOV (BRL)",
    "customers": "customers", "new_customers": "new customers", "returning_customers": "returning customers",
    "orders_per_customer": "orders per customer", "returning_share": "returning customers (%)",
    "new_revenue": "revenue from new customers (BRL)", "returning_revenue": "revenue from returning customers (BRL)",
    "repeat_rate_90d": "returned within 90 days (%)",
}


def complete_periods(freq):
    """Start dates of the periods fully inside the sales window: a week cut in half by the window edge would look like a drop."""
    every_period = pd.period_range(SALES_START, SALES_END, freq=freq)
    complete = (every_period.start_time >= SALES_START) & (every_period.end_time <= pd.Timestamp(SALES_END) + pd.Timedelta(days=1))
    return every_period[complete].start_time


def period_metrics(sold, period="day"):
    """Return one row per day, week or month of the sales window with orders, items, revenue and AOV.

    revenue is total_paid (what the customer paid, installment interest included), so AOV = revenue / orders.
    Periods with no orders stay in the table with 0 orders and an empty AOV, so plots show the gap.
    Only periods fully inside the sales window are kept (see complete_periods).
    """
    freq = PERIODS[period]
    period_start = sold["order_purchase_timestamp"].dt.to_period(freq).dt.start_time
    metrics = sold.groupby(period_start).agg(
        orders=("order_id", "count"),
        items=("n_items", "sum"),
        revenue=("total_paid", "sum"),
    )
    metrics = metrics.reindex(complete_periods(freq), fill_value=0)
    metrics.index.name = "period"
    metrics["aov"] = metrics["revenue"] / metrics["orders"].replace(0, np.nan)
    return metrics


def plot_metric(metrics, metric, period="day", subtitle=None, title=None):
    """Plot one metric, or a list of metrics in the same unit, from a period_metrics table and save it.

    Metrics in different units (revenue vs orders) belong in separate calls, never on a second y-axis.
    """
    columns = [metric] if isinstance(metric, str) else list(metric)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    for column, color in zip(columns, SERIES_COLORS):
        ax.plot(metrics.index, metrics[column], color=color, linewidth=2,
                solid_joinstyle="round", label=METRIC_LABELS[column])
    if len(columns) > 1:
        ax.legend(frameon=False, loc="upper left", labelcolor=TEXT_COLOR)
        ax.set_ylabel("count")
    else:
        ax.set_ylabel(METRIC_LABELS[columns[0]])
    ax.set_ylim(bottom=0)
    ax.yaxis.set_major_formatter(FuncFormatter(compact_number))
    ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="x", visible=False)

    title = title or f"{PERIOD_TITLES[period]} " + " and ".join(METRIC_LABELS[column] for column in columns)
    date_format = "%b %Y" if period == "month" else "%d %b %Y"
    subtitle = subtitle or "; ".join(
        f"{METRIC_LABELS[column]}: average {metrics[column].mean():,.0f} per {period}, "
        f"peak {metrics[column].max():,.0f} in {metrics[column].idxmax():{date_format}}"
        for column in columns
    )
    return save_plot(fig, f"{'_'.join(columns)}_{period}", title, subtitle)


def sales_over_time(orders):
    """Plot daily revenue, daily orders and items, and monthly AOV; return a monthly table of daily averages."""
    sold = sold_orders(orders)
    daily = period_metrics(sold, "day")
    monthly = period_metrics(sold, "month")
    plot_metric(daily, "revenue", "day")
    plot_metric(daily, ["orders", "items"], "day")
    plot_metric(monthly, "aov", "month")

    month = daily.index.to_period("M").start_time
    averages = daily.groupby(month)[["orders", "items", "revenue"]].mean()
    averages.columns = [f"{column}_per_day" for column in averages.columns]
    averages["aov"] = monthly["aov"]
    averages.index = averages.index.strftime("%Y-%m")
    averages.index.name = "month"
    print("\nDaily averages per month:")
    print(averages.round(2).to_string())
    return averages


def customer_orders(sold):
    """Add each customer's first order date and whether the order is a return visit.

    customer_unique_id is the real person. An order is returning only if it is placed on a later day than the
    customer's first order: several orders on the same day are one shopping session split up, not a comeback.
    The first order is taken from 2017 on; the few 2016 buyers are left out of the analysis and count as new in 2017.
    """
    customers = sold.copy()
    customers["purchase_date"] = customers["order_purchase_timestamp"].dt.normalize()
    customers["first_order_date"] = customers.groupby("customer_unique_id")["purchase_date"].transform("min")
    customers["is_returning"] = customers["purchase_date"] > customers["first_order_date"]
    return customers


def customer_period_metrics(sold, period="month"):
    """Return one row per day, week or month with new and returning customers, their orders and revenue.

    A customer is new in the period of their first order and returning in every later period they order in,
    so new_customers + returning_customers = customers. Revenue is split by order: a same-day second order
    still counts as new revenue.
    """
    freq = PERIODS[period]
    customers = customer_orders(sold)
    customers["period"] = customers["order_purchase_timestamp"].dt.to_period(freq).dt.start_time
    first_period = customers["first_order_date"].dt.to_period(freq).dt.start_time
    is_new_period = customers["period"] == first_period
    # nunique skips empty cells, so blanking the id counts only the matching customers
    customers["new_id"] = customers["customer_unique_id"].where(is_new_period)
    customers["returning_id"] = customers["customer_unique_id"].where(~is_new_period)
    customers["new_paid"] = customers["total_paid"].where(~customers["is_returning"], 0)
    customers["returning_paid"] = customers["total_paid"].where(customers["is_returning"], 0)

    metrics = customers.groupby("period").agg(
        customers=("customer_unique_id", "nunique"),
        new_customers=("new_id", "nunique"),
        returning_customers=("returning_id", "nunique"),
        orders=("order_id", "count"),
        new_revenue=("new_paid", "sum"),
        returning_revenue=("returning_paid", "sum"),
    )
    metrics = metrics.reindex(complete_periods(freq), fill_value=0)
    metrics.index.name = "period"
    metrics["orders_per_customer"] = metrics["orders"] / metrics["customers"].replace(0, np.nan)
    metrics["returning_share"] = 100 * metrics["returning_customers"] / metrics["customers"].replace(0, np.nan)
    return metrics


def repeat_rate(sold, within_days=90):
    """Share of customers (%) who order again on a later day within `within_days` of their first order, per first-order month.

    A customer whose first order is less than `within_days` before the end of the data has not had the full time
    to come back, so those months are left out instead of showing a fake drop.
    """
    customers = customer_orders(sold)
    first_order = customers.groupby("customer_unique_id")["first_order_date"].first()
    first_return = customers[customers["is_returning"]].groupby("customer_unique_id")["purchase_date"].min()
    days_to_return = (first_return.reindex(first_order.index) - first_order).dt.days
    returned = days_to_return <= within_days

    # keep only months whose every customer had the full window: the month holding the cutoff day is excluded too
    cutoff_month = (pd.Timestamp(SALES_END) - pd.Timedelta(days=within_days)).to_period("M").start_time
    cohort_month = first_order.dt.to_period("M").dt.start_time
    in_cohorts = cohort_month < cutoff_month
    rate = 100 * returned[in_cohorts].groupby(cohort_month[in_cohorts]).mean()
    rate = rate.rename(f"repeat_rate_{within_days}d")
    rate.index.name = "period"
    overall = 100 * returned[in_cohorts].mean()
    print(f"Returned within {within_days} days: {overall:.2f}% of customers (first order Jan 2017 to {rate.index[-1]:%b %Y})")
    return rate.to_frame(), overall


def customers_over_time(orders):
    """Plot new vs returning customers per month and the 90-day repeat rate per first-order month."""
    sold = sold_orders(orders)
    monthly = customer_period_metrics(sold, "month")
    plot_metric(monthly, ["new_customers", "returning_customers"], "month")
    plot_metric(monthly, "returning_share", "month",
                subtitle=f"share of each month's buyers who had bought before; average {monthly['returning_share'].mean():.1f}%")

    repeat, overall = repeat_rate(sold, within_days=90)
    plot_metric(repeat, "repeat_rate_90d", "month", title="90-day repeat rate",
                subtitle=f"by month of first order; {overall:.2f}% overall; orders on the same day as the first don't count")

    print("\nNew vs returning customers per month:")
    print(monthly.round(2).to_string())
    print("\n90-day repeat rate by month of first order (%):")
    print(repeat.round(2).to_string())
    return monthly, repeat


def new_vs_returning_customers(orders):
    """Count new vs returning customers, overall and per month, and plot the monthly ratio as 100% stacked bars.

    Per month, a customer is new in the month of their first order and returning in every later month they order in.
    Overall, each person counts once: "returned" means they ordered again on a later day at any point in the data.
    The returning slice is tiny, so its share is written above every bar.
    """
    sold = sold_orders(orders)
    monthly = customer_period_metrics(sold, "month")

    customers = customer_orders(sold)
    people = customers.groupby("customer_unique_id")["is_returning"].any()
    print(f"\nUnique customers: {len(people):,}; ordered again on a later day: {people.sum():,} ({100 * people.mean():.2f}%); "
          f"bought once (or only on one day): {(~people).sum():,}")
    print(f"Customer-months: {monthly['new_customers'].sum():,} new vs {monthly['returning_customers'].sum():,} returning "
          f"({100 * monthly['returning_customers'].sum() / monthly['customers'].sum():.2f}% returning)")

    fig, ax = plt.subplots(figsize=(10, 4.8))
    share_new = 100 - monthly["returning_share"]
    positions = np.arange(len(monthly))
    ax.bar(positions, share_new, color=SERIES_COLORS[0], label="new customers", width=0.75)
    ax.bar(positions, monthly["returning_share"], bottom=share_new, color=SERIES_COLORS[1], label="returning customers", width=0.75)
    for position, share in zip(positions, monthly["returning_share"]):
        ax.text(position, 101, f"{share:.1f}%", ha="center", va="bottom", fontsize=8, color=SERIES_COLORS[1])
    ax.set_xticks(positions[::3])
    ax.set_xticklabels(monthly.index[::3].strftime("%b %Y"))
    ax.set_ylim(0, 108)
    ax.set_ylabel("share of the month's customers (%)")
    ax.grid(axis="x", visible=False)
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2, labelcolor=TEXT_COLOR)
    save_plot(fig, "new_vs_returning_ratio_month", "New vs returning customers per month",
              f"orange labels = returning share; {people.sum():,} of {len(people):,} customers ({100 * people.mean():.1f}%) ever ordered again")
    return monthly


def growth_decomposition(orders, base=("2017-01-01", "2017-08-31"), new=("2018-01-01", "2018-08-31")):
    """Split revenue growth between two same-length periods into customers, orders per customer and AOV.

    revenue = customers x (orders / customer) x (revenue / order), so the three growth factors multiply to the
    revenue growth. Taking logs turns the product into a sum, so each factor gets a share of the total growth.
    The default compares Jan-Aug 2018 with Jan-Aug 2017: the same months, so seasonality cancels out.
    """
    sold = sold_orders(orders)
    purchase_date = sold["order_purchase_timestamp"].dt.normalize()

    def factors(period):
        window = sold[purchase_date.between(*period)]
        n_customers = window["customer_unique_id"].nunique()
        n_orders = len(window)
        revenue = window["total_paid"].sum()
        return pd.Series({"revenue": revenue, "customers": n_customers,
                          "orders_per_customer": n_orders / n_customers, "aov": revenue / n_orders, "orders": n_orders})

    before, after = factors(base), factors(new)
    table = pd.DataFrame({"before": before, "after": after})
    table["change_%"] = 100 * (table["after"] / table["before"] - 1)

    drivers = ["customers", "orders_per_customer", "aov"]
    log_growth = np.log(after / before)
    table.loc[drivers, "share_of_growth_%"] = 100 * log_growth[drivers] / log_growth["revenue"]
    print(f"\nGrowth decomposition, {base[0][:7]}..{base[1][:7]} -> {new[0][:7]}..{new[1][:7]}:")
    print(table.round(2).to_string())

    fig, ax = plt.subplots(figsize=(8, 3.6))
    labels = ["more customers", "more orders per customer", "higher AOV"]
    values = table.loc[drivers, "share_of_growth_%"]
    ax.barh(labels[::-1], values[::-1], color=BAR_COLOR, height=0.55)
    for y, value in enumerate(values[::-1]):
        ax.text(value + 1, y, f"{value:.0f}%", va="center", fontsize=9, color=TEXT_COLOR)
    ax.set_xlim(0, 110)
    ax.set_xlabel("share of revenue growth (%)")
    ax.grid(axis="y", visible=False)
    save_plot(fig, "growth_decomposition", "Where the revenue growth came from",
              f"revenue +{table.loc['revenue', 'change_%']:.0f}%: Jan-Aug 2018 vs Jan-Aug 2017 (log shares, factors multiply to revenue)")
    return table


BLACK_FRIDAY = "2017-11-24"
# (label, first day, last day): a 4-week baseline, the run-up week, the event week, December, and a 4-week "new normal"
BLACK_FRIDAY_PERIODS = [
    ("baseline (4 wks before)", "2017-10-20", "2017-11-16"),
    ("run-up week", "2017-11-17", "2017-11-23"),
    ("Black Friday week", "2017-11-24", "2017-11-30"),
    ("December", "2017-12-01", "2017-12-31"),
    ("after (4 wks, Jan-Feb)", "2018-01-08", "2018-02-04"),
]


def black_friday_test(orders):
    """Compare daily orders and revenue around Black Friday 2017 with the 4 weeks before it.

    Two questions: how big was the spike, and did it only pull sales forward (a dip afterwards) or did the baseline
    stay higher? Caveat: with only one Black Friday in the data, a higher level in Jan-Feb could also be general
    growth or seasonality; the same weeks of 2017 are not a clean comparison because the business was smaller.
    """
    daily = period_metrics(sold_orders(orders), "day")
    rows = []
    for label, start, end in BLACK_FRIDAY_PERIODS:
        window = daily.loc[start:end]
        rows.append({"period": label, "days": len(window), "orders_per_day": window["orders"].mean(),
                     "revenue_per_day": window["revenue"].mean(), "aov": window["revenue"].sum() / window["orders"].sum()})
    table = pd.DataFrame(rows).set_index("period")
    baseline = table.loc[BLACK_FRIDAY_PERIODS[0][0]]
    table["orders_vs_baseline_%"] = 100 * (table["orders_per_day"] / baseline["orders_per_day"] - 1)
    table["revenue_vs_baseline_%"] = 100 * (table["revenue_per_day"] / baseline["revenue_per_day"] - 1)

    # the same-weekday lift: Black Friday vs the four Fridays before it
    previous_fridays = daily.loc["2017-10-27":"2017-11-17"]
    previous_fridays = previous_fridays[previous_fridays.index.dayofweek == 4]
    spike = daily.loc[BLACK_FRIDAY]
    print(f"\nBlack Friday test (baseline = {BLACK_FRIDAY_PERIODS[0][1]} to {BLACK_FRIDAY_PERIODS[0][2]}):")
    print(table.round(1).to_string())
    print(f"\n{BLACK_FRIDAY}: {spike['orders']:,.0f} orders, {spike['orders'] / previous_fridays['orders'].mean():.1f}x the average of the 3 Fridays before; "
          f"revenue {spike['revenue'] / previous_fridays['revenue'].mean():.1f}x; AOV {spike['aov']:.0f} vs {previous_fridays['aov'].mean():.0f} on those Fridays")
    extra = (daily.loc["2017-11-24":"2017-11-30", "orders"] - baseline["orders_per_day"]).sum()
    print(f"Extra orders in Black Friday week vs baseline pace: {extra:,.0f}")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    window = daily.loc["2017-10-01":"2018-02-28"]
    ax.plot(window.index, window["orders"], color=BAR_COLOR, linewidth=2, solid_joinstyle="round")
    ax.axhline(baseline["orders_per_day"], color=TEXT_COLOR, linewidth=1, linestyle="--")
    ax.text(window.index[0], baseline["orders_per_day"] - 15, f"baseline {baseline['orders_per_day']:.0f}/day",
            fontsize=8, color=TEXT_COLOR, va="top", bbox={"facecolor": SURFACE_COLOR, "edgecolor": "none", "pad": 1})
    for label, start, end in BLACK_FRIDAY_PERIODS[1:3]:
        ax.axvspan(pd.Timestamp(start), pd.Timestamp(end) + pd.Timedelta(days=1), color=SERIES_COLORS[1], alpha=0.12, linewidth=0)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("orders per day")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="x", visible=False)
    after = table.loc[BLACK_FRIDAY_PERIODS[-1][0]]
    save_plot(fig, "black_friday_test", "Black Friday 2017: spike, then a higher baseline?",
              f"{spike['orders']:,.0f} orders on the day; Jan-Feb 2018 runs {after['orders_vs_baseline_%']:+.0f}% vs the 4 weeks before; shaded = run-up and event week")
    return table


REPEAT_WINDOW_DAYS = 90
# repeat rates are ~1%, so a segment needs many first-time buyers before its rate means anything
MIN_CUSTOMERS = 1000


def english_category(categories):
    """Translate Portuguese product category names to English with data_prep/category_name.csv.

    A category missing from the translation table keeps its original name, so nothing silently turns into NaN.
    """
    translation = pd.read_csv(PROCESSED_PATH.parent / "data_prep" / "category_name.csv")
    names = dict(zip(translation["product_category_name"], translation["product_category_name_english"]))
    return categories.map(lambda name: names.get(name, name))


def first_order_cohort(sold, within_days=REPEAT_WINDOW_DAYS):
    """Return one row per customer: their first order's attributes and whether they came back within `within_days`.

    Same rules as repeat_rate: a return is an order on a later day, and first-order months too close to the end of
    the data are dropped because those customers have not had the full window yet. Ties on the first day go to the
    earliest timestamp. Adds delay_days (delivered minus estimated date, positive = late) and freight_share.
    """
    customers = customer_orders(sold).sort_values(["order_purchase_timestamp", "order_id"])
    first = customers.groupby("customer_unique_id").head(1).set_index("customer_unique_id")
    first_return = customers[customers["is_returning"]].groupby("customer_unique_id")["purchase_date"].min()
    days_to_return = (first_return.reindex(first.index) - first["first_order_date"]).dt.days
    first["returned"] = days_to_return <= within_days

    cutoff_month = (pd.Timestamp(SALES_END) - pd.Timedelta(days=within_days)).to_period("M").start_time
    first = first[first["first_order_date"].dt.to_period("M").dt.start_time < cutoff_month].copy()
    first["delay_days"] = (first["order_delivered_customer_date"] - first["order_estimated_delivery_date"]).dt.total_seconds() / 86400
    first["freight_share"] = first["total_freight"] / first["order_value"]
    first["category"] = english_category(first["main_category"])
    return first


def wilson_interval(returned, size, z=1.96):
    """95% confidence interval (as fractions) for a share; stays sensible for small shares and small groups."""
    share = returned / size
    spread = 1 + z ** 2 / size
    centre = (share + z ** 2 / (2 * size)) / spread
    half = z * np.sqrt(share * (1 - share) / size + z ** 2 / (4 * size ** 2)) / spread
    return centre - half, centre + half


def repeat_by(cohort, group, min_customers=0):
    """Repeat rate (%) per group of first-order customers, with the 95% interval, sorted by the group order given.

    `group` is a column name or a Series aligned to the cohort. Groups under `min_customers` are dropped.
    """
    key = cohort[group] if isinstance(group, str) else group
    table = cohort.groupby(key, observed=True)["returned"].agg(customers="size", returned="sum")
    table = table[table["customers"] >= min_customers].copy()
    table["rate"] = 100 * table["returned"] / table["customers"]
    bounds = [wilson_interval(row.returned, row.customers) for row in table.itertuples()]
    table["low"] = [100 * low for low, _ in bounds]
    table["high"] = [100 * high for _, high in bounds]
    return table


def plot_repeat_rates(table, name, title, subtitle, overall, sort=False, highlight=0):
    """Dot-and-whisker plot of repeat rates: one row per group, 95% interval as the whisker, overall rate as a dashed line.

    The group size is written next to each label, so a wide whisker on a small group is visible at a glance.
    `highlight` colours the best and worst N groups in the second series colour.
    """
    table = table.sort_values("rate") if sort else table.iloc[::-1]
    colors = [BAR_COLOR] * len(table)
    if highlight:
        ranked = table["rate"].rank(method="first")
        colors = [SERIES_COLORS[1] if rank <= highlight or rank > len(table) - highlight else BAR_COLOR for rank in ranked]
    fig, ax = plt.subplots(figsize=(9, max(3, 0.38 * len(table) + 1.5)))
    positions = np.arange(len(table))
    ax.hlines(positions, table["low"], table["high"], color=colors, linewidth=2)
    ax.scatter(table["rate"], positions, color=colors, s=36, zorder=3)
    ax.axvline(overall, color=TEXT_COLOR, linewidth=1, linestyle="--")
    ax.set_yticks(positions)
    ax.set_yticklabels([f"{label}  (n={size:,})" for label, size in zip(table.index.astype(str), table["customers"])])
    ax.set_xlim(left=0)
    ax.set_xlabel(f"returned within {REPEAT_WINDOW_DAYS} days (%)")
    ax.grid(axis="y", visible=False)
    return save_plot(fig, name, title, f"{subtitle}; dashed = overall {overall:.2f}%; whiskers = 95% interval")


def delivery_and_review_vs_repeat(orders):
    """Do customers with a late first delivery or a bad first review return less? Plot and print both views.

    Delay is delivered minus estimated date; only delivered first orders have it. Late and bad review overlap
    (late orders get worse reviews), so the 2x2 table at the end separates them.
    Caveat: late deliveries are more common in far-away states, so this is not proof that lateness causes churn.
    """
    cohort = first_order_cohort(sold_orders(orders))
    overall = 100 * cohort["returned"].mean()
    print(f"\nFirst-time customers in full-window cohorts: {len(cohort):,}; returned within {REPEAT_WINDOW_DAYS} days: {overall:.2f}%")

    delivered = cohort[cohort["delay_days"].notna()]
    bands = pd.cut(delivered["delay_days"], [-np.inf, -14, -7, 0, 7, np.inf],
                   labels=["14+ days early", "7-14 days early", "0-7 days early", "1-7 days late", "more than 7 days late"])
    by_delay = repeat_by(delivered, bands.rename("delay"))
    print("\nRepeat rate by delivery delay of the first order:")
    print(by_delay.round(2).to_string())
    plot_repeat_rates(by_delay, "repeat_by_delivery_delay", "Repeat rate by delivery delay of the first order",
                      f"{len(delivered):,} delivered first orders", overall)

    reviewed = cohort["review_score"].fillna(0).astype(int).map(lambda score: f"{score} stars" if score else "no review")
    by_review = repeat_by(cohort, reviewed.rename("review"))
    by_review = by_review.reindex([f"{score} stars" for score in range(1, 6)] + ["no review"]).dropna(subset=["customers"])
    print("\nRepeat rate by review score of the first order:")
    print(by_review.round(2).to_string())
    plot_repeat_rates(by_review, "repeat_by_review_score", "Repeat rate by review score of the first order",
                      f"{len(cohort):,} first-time customers", overall)

    late = (delivered["delay_days"] > 0).map({True: "late", False: "on time or early"})
    bad_review = (delivered["review_score"] <= 3).map({True: "review 1-3", False: "review 4-5"})
    combined = repeat_by(delivered[delivered["review_score"].notna()], late.rename("delivery") + " / " + bad_review.rename("review"))
    print("\nLate vs on time, crossed with review (delivered first orders with a review):")
    print(combined.round(2).to_string())

    is_late = delivered["delay_days"] > 0
    late_rate, on_time_rate = delivered.loc[is_late, "returned"].mean(), delivered.loc[~is_late, "returned"].mean()
    standard_error = np.sqrt(late_rate * (1 - late_rate) / is_late.sum() + on_time_rate * (1 - on_time_rate) / (~is_late).sum())
    gap = 100 * (late_rate - on_time_rate)
    print(f"\nLate minus on-time repeat rate: {gap:+.2f} points (95% interval {gap - 196 * standard_error:+.2f} to {gap + 196 * standard_error:+.2f})")
    return by_delay, by_review, combined


def repeat_by_segment(orders, best_worst=2):
    """Repeat rate by product category, customer state and freight share of the first order, each plotted separately.

    Categories and states under MIN_CUSTOMERS first-time buyers are left out (their rates are mostly noise).
    Freight share = freight / order value, cut into 5 equal-sized groups. Prints the best and worst categories.
    """
    cohort = first_order_cohort(sold_orders(orders))
    overall = 100 * cohort["returned"].mean()

    by_category = repeat_by(cohort, "category", MIN_CUSTOMERS)
    by_state = repeat_by(cohort, "customer_state", MIN_CUSTOMERS)
    quintiles = pd.qcut(cohort["freight_share"], 5)
    quintiles = quintiles.cat.rename_categories([f"freight {max(0, 100 * interval.left):.0f}-{100 * interval.right:.0f}% of order" for interval in quintiles.cat.categories])
    by_freight = repeat_by(cohort, quintiles.rename("freight_share"))

    plot_repeat_rates(by_category, "repeat_by_category", "Repeat rate by product category of the first order",
                      f"categories with {MIN_CUSTOMERS:,}+ first-time customers; orange = best and worst {best_worst}",
                      overall, sort=True, highlight=best_worst)
    plot_repeat_rates(by_state, "repeat_by_state", "Repeat rate by customer state",
                      f"states with {MIN_CUSTOMERS:,}+ first-time customers", overall, sort=True)
    plot_repeat_rates(by_freight, "repeat_by_freight_share", "Repeat rate by freight share of the first order",
                      "5 equal-sized groups, cheapest freight on top", overall)

    ranked = by_category.sort_values("rate", ascending=False)
    for label, table in (("Repeat rate by category", ranked), ("Repeat rate by state", by_state.sort_values("rate", ascending=False)),
                         ("Repeat rate by freight share", by_freight)):
        print(f"\n{label}:")
        print(table.round(2).to_string())
    print(f"\nBest {best_worst} categories: {', '.join(ranked.index[:best_worst])}; worst {best_worst}: {', '.join(ranked.index[-best_worst:])}")
    return by_category, by_state, by_freight


def top_products(orders, how_many=5):
    """Print and plot the most purchased products and categories by units sold in the sales window.

    A unit is one row of order_items, counted only for orders that count as a sale. Product ids carry no name in
    the data, so each is labelled with its category and the first 6 characters of its id.
    """
    data_path = PROCESSED_PATH.parent / "data_prep"
    items = pd.read_csv(data_path / "order_items.csv", usecols=["order_id", "product_id", "price"])
    products = pd.read_csv(data_path / "products.csv", usecols=["product_id", "product_category_name"])
    items = items[items["order_id"].isin(sold_orders(orders)["order_id"])]
    items = items.merge(products, on="product_id", how="left").fillna({"product_category_name": "unknown"})
    items["product_category_name"] = english_category(items["product_category_name"])

    top = items.groupby("product_id").agg(units=("order_id", "size"), orders=("order_id", "nunique"),
                                          revenue=("price", "sum"), category=("product_category_name", "first"))
    top = top.sort_values("units", ascending=False).head(how_many)
    top.index = [f"{category} · {product_id[:6]}" for product_id, category in zip(top.index, top["category"])]
    categories = items.groupby("product_category_name").agg(units=("order_id", "size"), orders=("order_id", "nunique"),
                                                            revenue=("price", "sum")).sort_values("units", ascending=False).head(how_many)
    print(f"\nTop {how_many} products by units sold ({len(items):,} units in total):")
    print(top.drop(columns="category").round(0).to_string())
    print(f"\nTop {how_many} categories by units sold:")
    print(categories.round(0).to_string())

    for table, name, title in ((top, "top_products", "Most purchased products"), (categories, "top_categories", "Most purchased categories")):
        fig, ax = plt.subplots(figsize=(8, 3.6))
        ax.barh(table.index[::-1], table["units"][::-1], color=BAR_COLOR, height=0.55)
        for y, units in enumerate(table["units"][::-1]):
            ax.text(units, y, f" {units:,}", va="center", fontsize=9, color=TEXT_COLOR)
        ax.xaxis.set_major_formatter(FuncFormatter(compact_number))
        ax.set_xlabel("units sold")
        ax.grid(axis="y", visible=False)
        save_plot(fig, name, title, f"top {how_many} by units, {SALES_START[:7]} to {SALES_END[:7]}")
    return top, categories


if __name__ == "__main__":
    orders = load_orders()
    describe_columns(orders)
    averages = sales_over_time(orders)
    monthly_customers, repeat = customers_over_time(orders)
    new_vs_returning_customers(orders)
    growth_table = growth_decomposition(orders)
    black_friday = black_friday_test(orders)
    delivery_review = delivery_and_review_vs_repeat(orders)
    segments = repeat_by_segment(orders)
    popular = top_products(orders)
