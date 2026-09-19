import requests
import os
from dotenv import load_dotenv

load_dotenv()

APP_TOKEN = os.getenv("SOCRATA_APP_TOKEN")

# The classic, well-documented Socrata endpoint pattern - still fully
# supported alongside the newer SODA3 API. 311 Service Requests dataset,
# identified by its permanent Socrata UID: erm2-nwe9
BASE_URL = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"

HEADERS = {
    "X-App-Token": APP_TOKEN
}


def get_311_complaints(location, complaint_type=None, time_period_days=30):
    """
    Queries NYC's real 311 Service Requests dataset for a given location,
    optionally filtered by complaint type, within a recent time window.

    location: a borough name, or we can refine this to a more precise
              geographic filter once we test what the dataset actually
              supports well (zip code, cross streets, etc.)
    complaint_type: e.g. "Noise - Residential", "Illegal Parking" - must
                    match the dataset's actual category names, which we'll
                    confirm by testing
    time_period_days: how many days back to search, default 30
    """
    from datetime import datetime, timedelta, UTC

    since_date = (datetime.now(UTC) - timedelta(days=time_period_days)).strftime("%Y-%m-%dT%H:%M:%S")

    # SoQL query built as URL parameters, same pattern as every prior
    # API integration in this project
    where_clauses = [f"created_date > '{since_date}'"]

    if location:
        where_clauses.append(f"borough = '{location.upper()}'")

    if complaint_type:
        where_clauses.append(f"complaint_type = '{complaint_type}'")

    where_clause = " AND ".join(where_clauses)

    params = {
        "$where": where_clause,
        "$limit": 50,
        "$order": "created_date DESC",
    }

    try:
        response = requests.get(BASE_URL, headers=HEADERS, params=params, timeout=15)

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            print(f"Error response: {response.text[:500]}")
            return []

        data = response.json()
        print(f"Found {len(data)} complaints")
        return data

    except requests.exceptions.RequestException as e:
        print(f"Request error: {e}")
        return []


if __name__ == "__main__":
    # Simple test: any complaints in Brooklyn in the last 30 days
    results = get_311_complaints(location="Brooklyn", complaint_type="Noise - Residential")

    if results:
        print("\nSample result:")
        sample = results[0]
        print(f"  Type: {sample.get('complaint_type')}")
        print(f"  Description: {sample.get('descriptor')}")
        print(f"  Date: {sample.get('created_date')}")
        print(f"  Borough: {sample.get('borough')}")