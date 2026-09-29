import requests
import os
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

load_dotenv()

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")

# Open Parking and Camera Violations dataset, confirmed dataset ID: nc67-uf89
BASE_URL = "https://data.cityofnewyork.us/resource/nc67-uf89.json"

HEADERS = {
    "X-App-Token": APP_TOKEN
}

# This dataset uses abbreviated county codes, not full borough names -
# verified directly against real data, since 311's dataset uses full names
# and we can't assume consistency across different NYC datasets.
BOROUGH_TO_COUNTY_CODE = {
    "BROOKLYN": "K",
    "BRONX": "BX",
    "MANHATTAN": "NY",
    "QUEENS": "Q",
    "STATEN ISLAND": "ST",
}


def get_parking_violations(location):
    """
    Queries NYC's historical parking and camera violations dataset for a
    given borough. This dataset is a large historical archive, not a
    real-time feed - see the tool's schema description in tool_schemas.py
    for why time_period_days was removed (repeated testing couldn't find
    a reliable way to isolate "recent" records from this dataset - see
    EVAL_SET.md for the investigation).

    location: a borough name (e.g. "Brooklyn") - internally converted to
              this dataset's actual county code format. Verified directly
              against real data that at least K and BK both appear for
              Brooklyn - this dataset is inconsistent about county coding
              the same way building permits was inconsistent about
              capitalization. We filter for K only; BK-coded Brooklyn
              records are a known, accepted gap for now.
    """
    county_code = BOROUGH_TO_COUNTY_CODE.get(location.upper()) if location else None

    if location and not county_code:
        print(f"Warning: unrecognized borough '{location}', no county filter applied")

    where_clauses = []
    if county_code:
        where_clauses.append(f"county = '{county_code}'")
    where_clause = " AND ".join(where_clauses) if where_clauses else None

    params = {"$limit": 1000}
    if where_clause:
        params["$where"] = where_clause

    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"Error response: {response.text[:500]}")
            return []

        data = response.json()

        # issue_date is stored as plain MM/DD/YYYY text, not a real date
        # type. Genuinely malformed records exist (e.g. "70/40/2000") and
        # are dropped here rather than passed downstream. See
        # EVAL_SET.md for the investigation into why this dataset doesn't
        # support a reliable "recent" filter, and why time_period_days
        # was removed rather than fixed.
        valid_data = []
        for record in data:
            date_str = record.get("issue_date", "")
            try:
                parsed_date = datetime.strptime(date_str, "%m/%d/%Y")
                record["_parsed_date"] = parsed_date
                valid_data.append(record)
            except (ValueError, TypeError):
                print(f"  Skipping malformed record (bad date '{date_str}'): summons {record.get('summons_number')}")

        valid_data.sort(key=lambda r: r["_parsed_date"], reverse=True)
        for record in valid_data:
            del record["_parsed_date"]

        print(f"Found {len(data)} raw records, {len(valid_data)} valid after removing malformed dates")
        return valid_data[:50]

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []


if __name__ == "__main__":
    results = get_parking_violations(location="Brooklyn")

    if results:
        print("\nSample result (raw, unprocessed):")
        import json
        print(json.dumps(results[0], indent=2))
