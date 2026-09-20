import requests
import os
import json
from datetime import datetime, timedelta, UTC
from dotenv import load_dotenv

load_dotenv()

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")

# DOT Traffic Speeds dataset, confirmed dataset ID: i4gi-tjb9
# Replaces the originally planned Air Quality tool, which turned out to be
# aggregate, borough-level annual/seasonal indicators rather than live,
# individual-record data - structurally inconsistent with our other four
# tools. This dataset is a genuine live feed (112M rows, updated several
# times per day), with a real borough field and timestamp - a much closer
# structural match.
BASE_URL = "https://data.cityofnewyork.us/resource/i4gi-tjb9.json"

HEADERS = {
    "X-App-Token": APP_TOKEN
}


def get_traffic_speeds(location, hours_back=24, limit=50):
    """
    Queries NYC's real, live DOT Traffic Speeds dataset for a given
    borough within a recent time window - answers "how's traffic right
    now" for a given area.

    NOTE: despite being described as a live feed, real testing showed
    individual boroughs can have gaps of 6+ hours between updates - a
    6-hour window returned zero results even though data existed, simply
    because the most recent update for that borough was slightly older
    than the cutoff. Widened to 24 hours by default to reliably absorb
    this real-world staleness.

    location: a borough name (e.g. "Brooklyn")
    hours_back: how many hours back to search, default 24
    limit: how many records to return, default 50
    """
    now = datetime.now(UTC)
    since_time_obj = now - timedelta(hours=hours_back)
    since_time_str = since_time_obj.strftime("%Y-%m-%dT%H:%M:%S")

    where_clauses = [f"data_as_of > '{since_time_str}'"]

    if location:
        where_clauses.append(f"upper(borough) = '{location.upper()}'")

    where_clause = " AND ".join(where_clauses)

    params = {
        "$where": where_clause,
        "$limit": limit,
        "$order": "data_as_of DESC",
    }

    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"Error response: {response.text[:800]}")
            return []

        data = response.json()
        print(f"Found {len(data)} traffic speed records")
        return data

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []


if __name__ == "__main__":
    results = get_traffic_speeds(location="Brooklyn")

    if results:
        print("\nSample result:")
        sample = results[0]
        print(f"  Road: {sample.get('link_name')}")
        print(f"  Speed: {sample.get('speed')} mph")
        print(f"  As of: {sample.get('data_as_of')}")
        print(f"  Borough: {sample.get('borough')}")
