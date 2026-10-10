# MyBlock: Product Requirements Document

## Context

MyBlock was built to learn how AI agents work: tool use, the agent loop,
and evaluation. This PRD was written after the fact, to describe the
product it would be and to be honest about where the current version
falls short.

## 1. User and Problem

**User:** A curious, sometimes nosey New Yorker who wants to know what's
going on in their neighborhood, both right now and over time.

They ask two kinds of questions:

- **What's happening now?** Noise tonight, construction this week.
- **Is it changing?** More complaints than six months ago, more
  enforcement.

**Problem:** New Yorkers who want to know what's happening around them
mostly rely on Reddit, social media, and neighborhood groups. Those
sources are fast, but they're anecdotal, hard to verify, and can't
answer *is this getting worse?* The city publishes reliable data on
complaints, permits, parking, and traffic. But it's spread across
separate portals, it's hard to query, and it's written for analysts, not
residents.

**Assumption to test:** Twitter (X) used to fill part of this gap, and
as people have moved away from it, timely local information has become
harder to find. This is an observation, not measured.

**Opportunity:** Let a resident ask a plain question and get an answer
drawn from official city data. The answer should be honest about what
that data can and can't tell them.

## 2. Scope

**In scope**

- Answers plain-language questions about a NYC area using five official
  NYC Open Data sources:
  - 311 complaints
  - complaint trends (last 30 days vs. six months ago)
  - parking and camera violations
  - building permits
  - traffic speeds
- The agent decides which sources to check, in what order, and when it
  has enough to answer. Nothing is scripted.
- Answers state where the data came from, how recent it is, and what it
  doesn't cover.
- Questions outside its data, like "best restaurant" or "air quality,"
  get an honest "I can't answer that" instead of a forced answer.

**Out of scope (current version)**

- **Block or neighborhood precision.** All data is borough-level. The
  agent can narrow down using addresses in the records, but it tells the
  user the data is borough-wide.
- **True real-time.** Sources lag from hours to days, and the answer
  says so.
- **Accounts, saved locations, alerts, or any personal data.**
- **A user interface.** It currently runs from the command line.
- **Safety judgments.** It never calls an area "safe" or "quiet" just
  because data is missing.

## 3. Key Decisions and Tradeoffs

**The agent can decline (`tool_choice: auto`).** Claude decides whether
to call a tool at all. Forcing a tool call would guarantee an answer to
every question, including ones the data can't support. Being able to
decline honestly mattered more than always having an answer.

**Haiku 4.5 as the model.** It's fast and cheap, and it passed the eval
set once the prompt was fixed. A side-by-side comparison with larger
models hasn't been done yet.

**Act first, then explain limits.** An early version of the system
prompt made the agent ask permission before using borough-level data for
a neighborhood question. That was safe but less useful. The final rule:
always try the most useful tool, then state its limits. Only decline
when no tool could plausibly help.

**Tool descriptions are the interface.** Claude never sees the code,
only each tool's plain-English description. Two descriptions were
rewritten to prevent wrong answers:

- Parking is described as a historical archive with no recency claim.
- Traffic discloses that its feed lags.

**A limit on tool calls.** The agent stops after 5 tool calls as a
safety limit. It's checked once per round, so a round with several calls
at once can go slightly over 5.

## 4. How "Good" Is Measured

- 9 test questions covering in-scope, out-of-scope, ambiguous, and
  time-specific asks. Expected behavior was written for each one before
  any test ran.
- Scored on 7 dimensions:
  1. tool relevance
  2. sequencing
  3. restraint
  4. honest scope recognition
  5. handling empty or odd results
  6. grounding
  7. appropriate confidence
- **Baseline:** 5 pass, 1 partial, 3 fail. The failures came from a
  date-format bug and from the agent treating missing data as "safe."
- **After three prompt versions,** run 3 times per question: the
  time-of-day failure (Test 5) passed 3 of 3. Two inconsistencies
  remain:
  - Test 2 doesn't always check the trend tool.
  - Test 7 varies in the arguments it passes.

Full results are in `EVAL_SET.md`.

**If this were a real product,** I'd also track:

- how often answers cite their source and timestamp
- how often out-of-scope questions get an honest decline
- whether users ask follow-ups or rephrase, a sign the first answer
  missed

## 5. Risks and Known Limits

- **Granularity mismatch:** users think in neighborhoods, but the data
  is borough-level.
- **Data freshness:** sources lag from hours to days, and the parking
  dataset's recency is unresolved.
- **Data quality:**
  - Brooklyn appears under two county codes in the parking data, and
    only one is handled.
  - Some records have malformed dates.
  - Field formats vary across datasets.
- **Run-to-run variability:** the same question can produce different
  tool choices.
- **Misplaced trust:** a user could read an answer as safety advice. The
  prompt guards against this, but it's a risk if this grew.
- **Small eval set:** 9 questions, and none test a location with very
  little data.
- **Cost per question hasn't been measured.**

## 6. What's Next

1. A web interface, designed around the limits above: showing
   freshness, scope, and honest declines clearly.
2. Neighborhood-level answers, using the location coordinates many
   records already include.
3. Add an 8th eval dimension (completeness within honest limits) and a
   sparse-location test.
4. Compare models and measure cost per question.
