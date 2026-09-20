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


def get_parking_violations(location, time_period_days=30):
    """
    Queries NYC's real Open Parking and Camera Violations dataset for a
    given location within a recent time window.

    location: a borough name (e.g. "Brooklyn") - internally converted to
              this dataset's actual county code format (verified: K, BX,
              NY, Q, ST)
    time_period_days: how many days back to search, default 30
    """
    county_code = BOROUGH_TO_COUNTY_CODE.get(location.upper()) if location else None

    if location and not county_code:
        print(f"Warning: unrecognized borough '{location}', no county filter applied")

    # This dataset stores issue_date as plain MM/DD/YYYY text, not an ISO
    # timestamp like the 311 dataset - verified directly against real data.
    since_date_obj = datetime.now(UTC) - timedelta(days=time_period_days)
    since_date_str = since_date_obj.strftime("%m/%d/%Y")

    where_clauses = [f"issue_date > '{since_date_str}'"]

    if county_code:
        where_clauses.append(f"county = '{county_code}'")

    where_clause = " AND ".join(where_clauses)

    params = {
        "$where": where_clause,
        "$limit": 50,
        "$order": "issue_date DESC",
    }

    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"Error response: {response.text[:500]}")
            return []

        data = response.json()

        # NYC's real dataset contains occasional malformed records (verified
        # directly: found a real record with issue_date "70/40/2000",
        # state "99", license_type "999" - clearly corrupted/placeholder
        # data, not a bug in our code). Filter these out rather than pass
        # nonsensical data downstream to the agent.
        valid_data = []
        for record in data:
            date_str = record.get("issue_date", "")
            try:
                datetime.strptime(date_str, "%m/%d/%Y")
                valid_data.append(record)
            except (ValueError, TypeError):
                print(f"  Skipping malformed record (bad date '{date_str}'): summons {record.get('summons_number')}")

        print(f"Found {len(data)} violations, {len(valid_data)} valid after filtering malformed records")
        return valid_data

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []


if __name__ == "__main__":
    results = get_parking_violations(location="Brooklyn")

    if results:
        print("\nSample result (raw, unprocessed):")
        import json
        print(json.dumps(results[0], indent=2))
