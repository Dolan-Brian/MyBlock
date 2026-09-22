"""
Tool schema definitions for MyBlock's agent.

Each schema describes one real Python function to Claude - the name,
a plain-English description (the ONLY thing Claude reads to decide when
this tool is relevant), and the exact inputs it expects, in the format
Anthropic's API requires.

tool_choice is set to "auto" when we actually call the API - this is a
deliberate choice, not the default we happened to land on: it's what lets
Claude honestly recognize when a question falls outside all five tools'
scope, rather than being forced to call something irrelevant.
"""

TOOL_311_COMPLAINTS = {
    "name": "get_311_complaints",
    "description": (
        "Search NYC's official 311 service request records for a specific "
        "borough. Use this to answer questions about noise complaints, "
        "illegal parking, sanitation issues, or other quality-of-life "
        "complaints filed by residents. The complaint_type parameter should "
        "match how NYC categorizes complaints (e.g., 'Noise - Residential', "
        "'Illegal Parking', 'Dirty Conditions') - if unsure of the exact "
        "category, a partial or best-guess term is still useful. Can filter "
        "by how far back to search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The NYC borough to search (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island')."
            },
            "complaint_type": {
                "type": "string",
                "description": "The specific type of complaint to filter for, e.g. 'Noise - Residential'. Optional - omit to search all complaint types."
            },
            "time_period_days": {
                "type": "integer",
                "description": "How many days back to search. Defaults to 30 if not specified."
            }
        },
        "required": ["location"]
    }
}

TOOL_HISTORICAL_TREND = {
    "name": "get_historical_trend",
    "description": (
        "Compare complaint volume in a NYC borough between the most recent "
        "30 days and the same 30-day window from 6 months ago, to determine "
        "whether an area is trending better or worse over time. Use this "
        "when a question specifically asks about change over time, history, "
        "or trends - not for questions about what's happening right now, "
        "which get_311_complaints answers instead. The comparison window is "
        "fixed at 6 months back, based on real testing - not adjustable."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The NYC borough to check (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island')."
            },
            "complaint_type": {
                "type": "string",
                "description": "The specific type of complaint to check the trend for, e.g. 'Noise - Residential'. Optional - omit to check overall complaint trends."
            }
        },
        "required": ["location"]
    }
}

TOOL_PARKING_VIOLATIONS = {
    "name": "get_parking_violations",
    "description": (
        "Check NYC parking and camera violation records for a specific "
        "borough over a recent time window. Use this to answer direct "
        "questions about parking ticket risk or camera violations, and "
        "also as a useful proxy for related questions - such as whether an "
        "area has heavy alternate-side parking enforcement, whether "
        "visitors or non-residents frequently park there, or general "
        "patterns in how strictly parking is enforced in a neighborhood."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The NYC borough to check (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island')."
            },
            "time_period_days": {
                "type": "integer",
                "description": "How many days back to search. Defaults to 30 if not specified."
            }
        },
        "required": ["location"]
    }
}

TOOL_BUILDING_PERMITS = {
    "name": "get_building_permits",
    "description": (
        "Check NYC Department of Buildings permit records for a specific "
        "borough over a recent time window, showing construction, "
        "renovation, or new development activity. Use this to answer "
        "direct questions about construction or building work in an area, "
        "and also as a proxy for related questions - such as whether a "
        "neighborhood is actively changing or developing, whether there's "
        "likely to be construction noise or disruption, or general signs "
        "of real estate investment in the area."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The NYC borough to check (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island')."
            },
            "time_period_days": {
                "type": "integer",
                "description": "How many days back to search. Defaults to 180 if not specified, since permit activity is naturally less frequent than complaints."
            }
        },
        "required": ["location"]
    }
}

TOOL_TRAFFIC_SPEEDS = {
    "name": "get_traffic_speeds",
    "description": (
        "Check real-time NYC traffic speed data for roads in a specific "
        "borough. Use this to answer questions about current traffic "
        "conditions, congestion, or how fast vehicles are moving in an "
        "area right now. This is a live feed, but real testing has shown "
        "individual boroughs can have several hours of lag between "
        "updates - the most recent available data may not reflect the "
        "exact current moment, so treat results as 'recent' rather than "
        "'this instant.'"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "location": {
                "type": "string",
                "description": "The NYC borough to check (e.g., 'Brooklyn', 'Queens', 'Manhattan', 'Bronx', 'Staten Island')."
            },
            "hours_back": {
                "type": "integer",
                "description": "How many hours back to search for the most recent available data. Defaults to 24 if not specified, to reliably account for real feed lag."
            }
        },
        "required": ["location"]
    }
}

# All five tools together, in the format Claude's API expects when
# describing available tools for a given request.
ALL_TOOLS = [
    TOOL_311_COMPLAINTS,
    TOOL_HISTORICAL_TREND,
    TOOL_PARKING_VIOLATIONS,
    TOOL_BUILDING_PERMITS,
    TOOL_TRAFFIC_SPEEDS,
]
