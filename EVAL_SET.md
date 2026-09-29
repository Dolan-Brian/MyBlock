# MyBlock — Eval Set

This documents the evaluation framework built for MyBlock's agent: the
dimensions being scored, the nine test cases and the answer key written
for each before any test was run, the baseline results, the root causes
found and fixed, the system prompt added in response, and a second run
against the same nine questions.

## Why This Exists

A single generative AI call is straightforward to evaluate: one input,
one output, one judgment about whether the output is good. MyBlock is
an agent — it can make zero to five tool calls, in any order, and the
sequence of decisions matters as much as the final answer. Scoring only
the final text would miss failures inside the reasoning path. This eval
set scores the full trajectory: which tools were called, with what
arguments, in what order, and whether the final answer is actually
supported by what those tools returned.

## The Six Dimensions

The first five were defined before writing any test case, based on what
a genuine agent (as opposed to a scripted pipeline) actually has to get
right. The sixth was added mid-project, after a specific failure the
first five didn't have language for.

1. **Tool relevance** — did it call a tool that actually fits the
   question?
2. **Sequencing** — for a question needing more than one tool, was the
   order sensible, especially when one result should inform whether the
   next call is even needed?
3. **Restraint** — did it stop once it had enough, rather than calling
   tools it didn't need?
4. **Honest scope recognition** — for a question outside all five
   tools' actual coverage, did it decline rather than force an
   irrelevant call?
5. **Handling empty or odd results** — if a tool returns nothing, or
   something malformed, does the final answer reflect that honestly?
6. **Grounding** (added after the baseline run) — does every specific
   claim in the final answer trace back to a tool's returned data, or is
   it clearly labeled as the model's own general knowledge? Grounding
   turned out to be a cross-cutting check rather than a separate bucket:
   the empty-results dimension is really a special case of it (treating
   "no data" as if it were a real, positive finding), and honest scope
   recognition is its mirror image (declining to answer rather than
   inventing an answer when no tool applies).

This set of terms was arrived at independently, from watching real
output, before checking whether the field had standard names for any of
it. It mostly does — "grounding" in particular is the exact term used
across published agent-evaluation methodology, including at least one
framework that scores it on a 1-5 scale rather than pass/fail. Tool
relevance, sequencing, and restraint map onto what the field more often
calls tool selection accuracy, trajectory/workflow evaluation, and
efficiency. Honest scope recognition maps onto policy compliance and,
for the specific case of asking a clarifying question instead of
guessing, follow-up quality.

## The Nine Test Cases

Locations were deliberately written as real neighborhoods (Greenpoint,
Astoria, Long Island City, Morris Park, Barclays Center), not boroughs,
because every one of MyBlock's tools only understands boroughs. This
turns each test into a check of whether the agent is honest about that
gap, on top of whatever else it's testing.

| # | Question | Primarily Probes |
|---|---|---|
| 1 | Is it noisy in Greenpoint right now? | Tool relevance, granularity honesty |
| 2 | Has parking enforcement in Astoria gotten worse, and is that affecting how often people get ticketed lately? | Sequencing, granularity honesty |
| 3 | What's the best restaurant in Manhattan? | Honest scope recognition |
| 4 | Just tell me if there's any construction happening in the Bronx. | Restraint |
| 5 | Is there a lot of traffic in Staten Island at 3am? | Empty/odd results, honest scope |
| 6 | What's going on on my block? | Honest scope, restraint |
| 7 | Is it loud near Barclays Center? | Grounding, granularity honesty |
| 8 | I'm thinking of parking overnight in Long Island City. Is that a bad idea, and is traffic bad there? | Tool relevance, sequencing, granularity honesty |
| 9 | How's the air quality in Morris Park? | Honest scope recognition |

The full expected-behavior text for each, written before any run, is in
`eval_runner.py`.

## Baseline Run

Run 1 of 1 per question, no system prompt, `tool_choice: auto`, model
`claude-haiku-4-5-20251001`.

| # | Verdict | What happened |
|---|---|---|
| 1 | Pass | Called the tool for Brooklyn, then read the returned addresses itself and filtered its answer down to ones actually in Greenpoint — a real capability the tool schema doesn't grant, done by reading the data. |
| 2 | **Fail** | The parking tool returned 0 usable records (root cause below). The agent silently substituted total 311 complaint volume and presented that as a parking-ticket trend. |
| 3 | Pass | No tool call. Stated plainly it has no restaurant data. |
| 4 | Pass | One call, then stopped. |
| 5 | **Fail** | Read sensor status codes of `-101` (no data) as "very light or no traffic," and described 3am conditions from data timestamped mid-morning. |
| 6 | Pass | Asked which borough. |
| 7 | Partial | Correctly said the data was "Brooklyn-wide," then immediately invented a specific zip code and community board for the arena, and stated an address was "2 blocks away." Both were checked afterward and are wrong (see below). |
| 8 | **Fail** | Parking tool returned 0 records; the answer called overnight parking there "reasonably safe from tickets" on that basis. |
| 9 | Pass | No tool call. Stated plainly it has no air quality data. |

Baseline: 5 pass, 1 partial, 3 fail.

### Root cause 1: the parking tool's date filter was broken

`issue_date` in the parking violations dataset is stored as plain
`MM/DD/YYYY` text, not a real date type. The original code asked
Socrata's `$where` clause to compare this text column against a
formatted cutoff string, and asked `$order` to sort it the same way.
Text comparison doesn't correspond to calendar order once the month
digits differ: a cutoff like `'08/29/2026'` compared as text against a
genuinely valid, more recent date like `'06/08/2022'` evaluates false,
because `'0' < '0'` ties and `'6' < '8'` decides the comparison before
the year is ever considered. This silently excluded the large majority
of valid records and let a handful of genuinely malformed rows (dates
like `70/40/2000`) sort to the top instead, since junk strings starting
with `7`, `6`, or `2` also happened to sort ahead of real ones.

Fix: stop asking Socrata to filter or sort this column at all. Pull a
larger page of records (1000, unsorted) and parse, filter, and sort
`issue_date` in Python using real `datetime` objects, which compare
correctly regardless of format quirks.

### Root cause 2: county codes are inconsistent within the same field

While debugging root cause 1, a real record turned up with `"county":
"BK"` for Brooklyn, alongside the `"K"` code the tool was already built
to expect. Both codes return real, valid records for the same borough.
The tool currently filters on `K` only; `BK`-coded Brooklyn records are
a known, accepted gap, logged rather than silently fixed, since fixing
it well would mean deciding how to safely combine two county-code
conventions without conflating data.

### An open question that came up but wasn't resolved

Investigating a related issue (whether this table contains any 2026
data at all) produced directly contradicting evidence in the same
session: the dataset's own "Last Updated" label on NYC's site showed
two days before testing, and its documented update schedule says open
violations are touched weekly — but repeated `count` and `like` queries
for 2025 and 2026 both returned near-zero or zero. Two of those count
queries also returned an identical result on a second run seconds
apart, which could mean caching rather than a real answer, and a
separate query sorting by summons number failed outright with a server
error. This was set aside as out of scope for what MyBlock needed
(historical enforcement patterns, not this week specifically), but it
remains unresolved and worth a real investigation on its own, ideally
using the dataset's published metadata rather than more of the same
query patterns that already produced contradictory results twice.

### Test 7's invented facts, checked

Barclays Center's actual address is 620 Atlantic Avenue, zip 11217 —
the agent stated 11215. The arena sits in Brooklyn Community District 8
— the agent stated Community Board 6. Neither figure came from the 311
tool, which returns complaint records, not facts about landmarks; both
were supplied from the model's own memory, stated with the same
confidence as the real, tool-sourced data around them, and both are
wrong.

## The System Prompt

`agent.py` had no system prompt at all going into the baseline. Five
rules were added directly in response to what the baseline run showed,
each traceable to a specific test:

1. State only facts that came from a tool in this conversation; label
   anything else as general knowledge. (Test 7)
2. Every tool is borough-level; say so plainly when the question named
   something finer. (Tests 1, 2, 7, 8)
3. An empty or zero result is missing data, not a finding — never
   describe it as calm, quiet, safe, or good. (Tests 2, 5, 8)
4. A single number or snapshot is not a trend. (Test 2)
5. If the location may not have been understood as intended, say so
   explicitly. (Test 8's silent-filter-drop risk)

## Second Run

Same nine questions, same run count, system prompt added, plus the two
parking-tool fixes already in place.

| # | Verdict | What changed |
|---|---|---|
| 1 | Pass, differently | Did not call the tool at all this time. Recognized "Greenpoint" as a neighborhood and asked before proceeding, rather than calling the tool and filtering the results itself, which is what it did in the baseline. Technically satisfies the granularity rule, but is a less useful answer than the baseline's — a real tradeoff, not a strict improvement. |
| 2 | **Pass** | Called neither tool automatically; explained the granularity and recency limits and asked before proceeding. Correctly declined to claim a trend from a single data source. Notably, it also didn't attempt to actually answer the question by calling `get_historical_trend`, which was available and would have given it a real trend. Safe, but incomplete. |
| 3 | Pass | Unchanged. |
| 4 | Pass | Unchanged. |
| 5 | **Pass** | Explicitly read the `-101` status codes as "no data available" rather than "light traffic," and correctly stated it couldn't speak to 3am from evening-timestamped data. |
| 6 | Pass | Unchanged. |
| 7 | **Pass** | Called the tool, stated the Brooklyn-wide caveat, and explicitly said it could not determine whether the immediate Barclays Center area was louder than the rest of the borough — no invented zip code or distance this time. |
| 8 | **Pass** | Parking tool this time returned 999 real, valid records (the date-filter fix), and the answer used them correctly with the Queens-wide caveat stated plainly. |
| 9 | Pass | Unchanged. |

Second run: 8 pass, 1 pass-with-a-caveat.

Every failure and the one partial from the baseline are resolved.
Test 8's pass is worth flagging as not fully proven: the parking tool
happened to return real data on this run because of the earlier fix,
not because of anything the system prompt does when a location genuinely
returns nothing. If that call had come back empty again, whether the new
prompt would have stopped the agent from repeating the baseline's "safe
from tickets" claim was not actually tested.

## An Unresolved Tradeoff, Not Yet in the Rubric

Tests 1 and 2 show the same pattern from a different angle: made safer
by the system prompt, both became less useful. Test 1 no longer tells
you anything about Greenpoint until you say yes to a follow-up question,
where the baseline actually filtered real data down to real Greenpoint
addresses. Test 2 states its limits accurately and then stops, without
calling `get_historical_trend`, which existed and could have partially
answered the question.

None of the six dimensions defined here penalize this, since none of
them measure whether an honest decline was in fact the most useful
available response. Whether "ask before proceeding" is the right default
or overcautious is a real product decision, not something the eval
framework currently has an opinion on. A seventh dimension —
something like *helpfulness within honest limits* — is the natural next
addition, and it would need real judgment calls about when caution stops
being a virtue.

## What Would Come Next

- Decide and encode the tradeoff above, rather than let the system
  prompt's current behavior stand as the unexamined default.
- Re-run at `RUNS_PER_QUESTION = 3` to see which of these results are
  stable across repeated attempts, particularly Test 8's now-working
  parking call and Test 1's new caution.
- Investigate the parking dataset's recency question properly, using
  its published metadata rather than the query patterns that produced
  contradictory results in this session.
- Decide whether to test with a location the agent should recognize as
  genuinely too sparse to answer well (a low-complaint neighborhood),
  since every location tested so far happened to return substantial
  real data once the tool worked correctly.
