"""Simple, transparent cycle estimates. These are not medical predictions."""
from datetime import date, datetime, timedelta


def parse_date(value):
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def cycle_summary(period_rows):
    # Input rows are ordered newest first; ignore malformed dates defensively.
    starts = []
    for row in period_rows:
        try:
            starts.append(parse_date(row["start_date"]))
        except (ValueError, TypeError, KeyError):
            pass
    starts = sorted(set(starts))
    intervals = [(starts[i] - starts[i - 1]).days for i in range(1, len(starts))]
    intervals = [n for n in intervals if 15 <= n <= 60]
    average = round(sum(intervals) / len(intervals)) if intervals else 28
    last_start = starts[-1] if starts else None
    next_period = last_start + timedelta(days=average) if last_start else None
    ovulation = next_period - timedelta(days=14) if next_period else None
    fertile_start = ovulation - timedelta(days=5) if ovulation else None
    fertile_end = ovulation + timedelta(days=1) if ovulation else None
    return {
        "last_start": last_start,
        "average_cycle": average,
        "next_period": next_period,
        "ovulation": ovulation,
        "fertile_start": fertile_start,
        "fertile_end": fertile_end,
        "cycles_counted": len(intervals),
    }


def fmt_day(value):
    return value.strftime("%b %d, %Y") if value else "Not enough data yet"
