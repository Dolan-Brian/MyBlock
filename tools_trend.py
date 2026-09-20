import requests
import os
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

load_dotenv()

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")
BASE_URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

HEADERS = {
    "X-App-Token": APP_TOKEN
}


def get_historical_trend(location, complaint_type=None, months_back=6):
    """
    Compares complaint volume in the most recent 30 days against the same
    30-day window from further back, to answer whether a location is
    trending better or worse over time - not just a current snapshot.

    location: borough name
    complaint_type: optional, e.g. "Noise - Residential"
    months_back: how far back to compare against, default 6 months
    """
    now = datetime.now(UTC)

    # Recent window: last 30 days
    recent_start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

    # Comparison window: 30 days, starting `months_back` months ago
    comparison_end = (now - timedelta(days=months_back * 30)).strftime("%Y-%m-%dT%H:%M:%S")
    comparison_start = (now - timedelta(days=months_back * 30 + 30)).strftime("%Y-%m-%dT%H:%M:%S")

    def count_complaints(start_date, end_date=None):
        where_clauses = [f"created_date > '{start_date}'"]
        if end_date:
            where_clauses.append(f"created_date < '{end_date}'")
        if location:
            where_clauses.append(f"borough = '{location.upper()}'")
        if complaint_type:
            where_clauses.append(f"complaint_type = '{complaint_type}'")

        where_clause = " AND ".join(where_clauses)

        # Use SoQL's count() function to get a total, rather than pulling
        # every row - much more efficient for this kind of aggregate question
        params = {
            "$where": where_clause,
            "$select": "count(*) as total",
        }

        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

        if response.status_code != 200:
            print(f"Error response: {response.text[:300]}")
            return None

        data = response.json()
        if data and "total" in data[0]:
            return int(data[0]["total"])
        return 0

    recent_count = count_complaints(recent_start)
    comparison_count = count_complaints(comparison_start, comparison_end)

    result = {
        "location": location,
        "complaint_type": complaint_type or "all types",
        "recent_window": f"{recent_start} to now",
        "comparison_window": f"{comparison_start} to {comparison_end}",
        "recent_30_day_count": recent_count,
        "comparison_30_day_count_from_months_ago": comparison_count,
        "months_back_compared": months_back,
    }

    if recent_count is not None and comparison_count is not None and comparison_count > 0:
        pct_change = ((recent_count - comparison_count) / comparison_count) * 100
        result["percent_change"] = round(pct_change, 1)
        result["trend"] = "worsening" if pct_change > 10 else "improving" if pct_change < -10 else "stable"

    return result


if __name__ == "__main__":
    result = get_historical_trend(location="Brooklyn", complaint_type="Noise - Residential", months_back=6)
    print(result)
