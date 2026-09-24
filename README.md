# MyBlock

An AI agent that autonomously decides which real NYC civic data sources to
check, and in what order, to answer open-ended questions about a
neighborhood or block.

## The Problem

There is one question every New Yorker has asked: "What's happening on my
block?" It could be construction, it could be a block party, it could be
a runaway cow. This is a genuinely open-ended question, and I thought it
was the perfect one to build my first agent around.

## What It Does

MyBlock gives Claude five real tools, each backed by a live NYC Open Data
source, and lets it decide - live, based on the specific question - which
to call, in what order, and when it has enough information to answer.
Nothing about the sequence is hardcoded.

**The five tools:**

1. **311 Complaints** - real-time complaint records (noise, sanitation,
   illegal parking, and more), filterable by type and time window
2. **Historical Trend** - compares recent complaint volume against the
   same window 6 months ago, to answer whether an area is improving or
   declining
3. **Parking & Camera Violations** - ticket and camera violation records,
   also used as a proxy for enforcement intensity and visitor/non-resident
   parking patterns
4. **Building Permits** - active construction and renovation activity,
   also used as a proxy for neighborhood change and development pressure
5. **Traffic Speeds** - a live feed of vehicle speeds on NYC roads

All five pull from official, sanctioned NYC Open Data APIs (Socrata) -
no scraping, consistent with the same principle applied to every project
in this portfolio.

## Why This Is a Genuine Agent, Not a Pipeline

`tool_choice` is deliberately set to `auto`, not `any` or a forced tool.
This was a specific, considered decision: `any` would force Claude to call
some tool even for a question outside all five tools' actual scope,
producing a misleading answer built on an irrelevant lookup. `auto`
preserves Claude's ability to honestly recognize when a question falls
outside what MyBlock can actually answer, rather than faking confidence.

The agent runs in a loop (see `agent.py`): call Claude, check whether it
requested a tool, execute the real function if so, send the real result
back, and repeat - up to a hard safety limit of 5 total tool calls - until
Claude has enough information to answer. The sequence of which tools get
called, and in what order, is decided fresh for every question.

## Real Data, Real Problems

Every one of the five tools required genuine debugging against real,
messy government data before it worked correctly:

- **Parking violations** store boroughs as abbreviated county codes
  (`K` for Brooklyn, not the full name), use `MM/DD/YYYY` dates, and
  contain real malformed records (an actual violation with an issue date
  of "70/40/2000") that are now filtered out defensively.
- **Building permits**: the obvious, well-documented dataset turned out to
  be a legacy system frozen since 2020. The current, correct dataset
  stores `borough` with genuinely inconsistent capitalization across
  records ("Queens", "MANHATTAN", "Brooklyn" all appear as real values),
  requiring a case-insensitive comparison.
- **Traffic speeds**: despite being described as a live feed, individual
  boroughs can go several hours without an update. An initial 6-hour
  lookback window returned zero results for real, existing data simply
  because the most recent update was slightly older than the cutoff.

None of these were hypothetical edge cases - each one was found by running
real queries and reading the actual raw responses, not by assuming
documentation was accurate.

## Tool Descriptions Are the Actual Interface

Claude never sees this project's Python code. It only sees the plain-
English description written for each tool - which is the entire basis for
every decision it makes about when a tool is relevant. Several
descriptions deliberately go beyond the tool's literal function: parking
violations are framed as a proxy for enforcement intensity and visitor
traffic, not just ticket counts, and the traffic speeds tool's description
explicitly warns about real feed lag, so Claude can reason about data
recency rather than assume it's instantaneous.

## Tech Stack

- Python
- Anthropic API (tool use / function calling)
- NYC Open Data (Socrata API)

## Status

Core agent loop is complete and tested against real, varied questions
across all five tools. A formal eval set - defining what "good" agent
behavior looks like across tool relevance, sequencing, restraint, honest
scope recognition, and graceful handling of empty results - is in
progress.

## Author

Brian Dolan - [LinkedIn](https://linkedin.com/in/DolanBrian) · [GitHub](https://github.com/dolan-brian)
