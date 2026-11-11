import sys
import time
from pathlib import Path

from data_profiling import ProfileReport

sys.path.insert(0, str(Path(__file__).resolve().parent))
from eda_analysis import load_orders, sold_orders

REPORT_PATH = Path(__file__).resolve().parent / "profiling_reports"


def profile_orders(orders, name, minimal=False):
    """Run fg-data-profiling on one table, save the HTML report and print how long it took.

    The timing is the point: it is what I compare with my own EDA flow.
    """
    REPORT_PATH.mkdir(exist_ok=True)
    start = time.perf_counter()
    report = ProfileReport(orders, title=name, minimal=minimal)
    report.to_file(REPORT_PATH / f"{name}.html")
    seconds = time.perf_counter() - start
    print(f"{name}: {len(orders):,} rows x {orders.shape[1]} columns, {seconds:.1f}s")
    return report


if __name__ == "__main__":
    orders = load_orders()
    # same table my own EDA starts from, nothing filtered: what the profiler sees by default
    profile_orders(orders, "orders_enriched_all")
    # same table after my sales filter: shows what the business rules change
    profile_orders(sold_orders(orders), "orders_enriched_sold")
