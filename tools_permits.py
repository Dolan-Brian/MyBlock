import requests
import os
import json
from dotenv import load_dotenv

load_dotenv()

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")

# DOB NOW: Build - Approved Permits dataset, ID: rbx6-tga4
# Switched from the legacy DOB Permit Issuance dataset (ipu4-2q9a) after
# discovering that dataset only contains records through 2020 - NYC's own
# documentation explicitly notes it's a legacy BIS dataset, superseded by
# DOB NOW for current permits. Verified by checking actual returned dates,
# which all clustered in 2020 regardless of our date filter.
BASE_URL = "https://data.cityofnewyork.us/resource/rbx6-tga4.json"

HEADERS = {
    "X-App-Token": APP_TOKEN
}


def get_building_permits(location, time_period_days=90, limit=50):
    """
    Queries NYC's real, currently-active DOB NOW Approved Permits dataset
    for a given location within a recent time window - answers "what's
    being built or renovated here."

    NOTE: field names verified directly against real data: borough,
    issued_date (ISO format, e.g. "2026-03-10T00:00:00.000"). Also
    discovered: this dataset stores borough with inconsistent
    capitalization across records ("Queens", "MANHATTAN", "Brooklyn" all
    appear as real values) - a genuine data quality issue in NYC's own
    system, not something we can control. Using SoQL's upper() function
    on both sides of the comparison makes the filter resilient to this.

    location: a borough name (e.g. "Brooklyn")
    time_period_days: how many days back to search, default 90
    """
    from datetime import datetime, timedelta, UTC

    since_date_obj = datetime.now(UTC) - timedelta(days=time_period_days)
    since_date_str = since_date_obj.strftime("%Y-%m-%dT00:00:00.000")

    where_clauses = [f"issued_date > '{since_date_str}'"]

    if location:
        where_clauses.append(f"upper(borough) = '{location.upper()}'")

    where_clause = " AND ".join(where_clauses)

    params = {
        "$where": where_clause,
        "$limit": limit,
        "$order": "issued_date DESC",
    }

    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"Error response: {response.text[:800]}")
            return []

        data = response.json()
        print(f"Found {len(data)} permits")
        return data

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []


if __name__ == "__main__":
    results = get_building_permits(location="Brooklyn")

    if results:
        print("\nSample result:")
        sample = results[0]
        print(f"  Work type: {sample.get('work_type')}")
        print(f"  Description: {sample.get('job_description')}")
        print(f"  Issued: {sample.get('issued_date')}")
        print(f"  Borough: {sample.get('borough')}")
