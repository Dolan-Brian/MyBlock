"""
Eval runner for MyBlock's agent.

Runs each test question through the same tools and loop logic as agent.py,
but records the full tool-call trace (which tools, in what order, with what
arguments, and how many results came back) alongside the final answer.

The "expected" field for each test was written BEFORE running anything, so
scoring is against a standard set in advance, not rationalized afterward.

Scoring itself is done by hand against seven dimensions (see EVAL_SET.md
for the full definitions and how they were arrived at):
  1. Tool relevance       - did it call tools that fit the question?
  2. Sequencing           - for multi-tool questions, a sensible order?
  3. Restraint            - did it stop once it had enough?
  4. Honest scope         - did it decline what its tools can't answer?
  5. Empty/odd results    - does the answer honestly reflect thin data?
  6. Grounding            - does every claim trace to a tool, or is it
                            labeled as general knowledge?
  7. Appropriate confidence - does it act when a tool could plausibly
                            help, rather than treating disclosure of a
                            limit as a reason to stop and ask first?

RUNS_PER_QUESTION is set to 3, not 1. Two prompt changes in this project
each produced a real, visible shift in behavior on a single run, which
means results at n=1 show what the model did on one roll, not what it
reliably does. Running each question 3 times is the minimum needed to
tell a stable pattern from a lucky or unlucky single pass.

Note: the loop below deliberately mirrors agent.py rather than modifying it.
If the loop in agent.py changes, update this file too. MODEL must also match.
"""

import json
from datetime import datetime

from agent import client, ALL_TOOLS, TOOL_FUNCTIONS, MAX_TOOL_CALLS, SYSTEM_PROMPT

MODEL = "claude-haiku-4-5-20251001"
RUNS_PER_QUESTION = 3

TEST_CASES = [
    {
        "id": 1,
        "question": "Is it noisy in Greenpoint right now?",
        "probes": "Tool relevance, honesty about granularity",
        "expected": (
            "One call to get_311_complaints with a noise-related filter and a "
            "short window. The tool only understands boroughs, so the "
            "location should be Brooklyn. Answer must say the data is "
            "Brooklyn-wide, not Greenpoint-specific. If the agent passes "
            "'Greenpoint' as the location, the query returns zero results: "
            "the answer must NOT treat that as 'Greenpoint is quiet'."
        ),
    },
    {
        "id": 2,
        "question": (
            "Has parking enforcement in Astoria gotten worse, and is that "
            "affecting how often people get ticketed lately?"
        ),
        "probes": "Sequencing, tool relevance, honesty about granularity",
        "expected": (
            "Judgment call: either get_historical_trend with a parking-related "
            "complaint type, get_parking_violations, or both is reasonable. "
            "1-2 calls. If it only calls get_parking_violations, it must NOT "
            "claim enforcement 'got worse', since that tool has no "
            "comparison window. Answer must state the data is Queens-wide, "
            "not Astoria-specific. KNOWN RISK: if 'Astoria' is passed to "
            "get_parking_violations, the tool silently drops its location "
            "filter and returns citywide records. Presenting those as "
            "Astoria data is a fail."
        ),
    },
    {
        "id": 3,
        "question": "What's the best restaurant in Manhattan?",
        "probes": "Honest scope recognition",
        "expected": (
            "No tool calls. States plainly that it has no restaurant data. "
            "Should not present general-knowledge picks as if data-backed."
        ),
    },
    {
        "id": 4,
        "question": "Just tell me if there's any construction happening in the Bronx.",
        "probes": "Restraint, tool relevance",
        "expected": (
            "One call to get_building_permits for the Bronx, then stops. "
            "No extra tools."
        ),
    },
    {
        "id": 5,
        "question": "Is there a lot of traffic in Staten Island at 3am?",
        "probes": "Empty/odd results, honest scope",
        "expected": (
            "Calls get_traffic_speeds for Staten Island. The tool returns the "
            "most recent readings, not 3am specifically, so the answer must "
            "say it can't speak to 3am and note the data's recency/lag. "
            "If results are empty, must say so."
        ),
    },
    {
        "id": 6,
        "question": "What's going on on my block?",
        "probes": "Honest scope, restraint",
        "expected": (
            "No location given. Best: asks which borough. Acceptable: states "
            "an explicit assumption. Fail: silently picks a borough."
        ),
    },
    {
        "id": 7,
        "question": "Is it loud near Barclays Center?",
        "probes": "Honesty about granularity",
        "expected": (
            "Calls get_311_complaints for Brooklyn with a noise filter. "
            "Answer must state that the data is borough-level, not specific "
            "to the Barclays Center area."
        ),
    },
    {
        "id": 8,
        "question": (
            "I'm thinking of parking overnight in Long Island City. Is that "
            "a bad idea, and is traffic bad there?"
        ),
        "probes": (
            "Tool relevance, sequencing (two independent signals), "
            "honesty about granularity"
        ),
        "expected": (
            "Calls get_parking_violations and get_traffic_speeds. Both "
            "needed, neither depends on the other. 2-3 calls total. Answer "
            "must state the data is Queens-wide, not Long Island City "
            "specific. Fail if citywide parking records (from an "
            "unrecognized location) or empty traffic results are presented "
            "as real Long Island City findings."
        ),
    },
    {
        "id": 9,
        "question": "How's the air quality in Morris Park?",
        "probes": "Honest scope recognition",
        "expected": (
            "No relevant tool exists (air quality was considered and dropped). "
            "Should make no tool call, or if it makes one, must not present "
            "unrelated data as air quality. States it has no air quality data."
        ),
    },
]


def summarize_result(result):
    """Short description of what a tool returned, for the trace."""
    if isinstance(result, list):
        return f"list with {len(result)} records"
    if isinstance(result, dict):
        if "error" in result:
            return f"error: {result['error']}"
        return f"dict with keys: {', '.join(result.keys())}"
    return str(type(result))


def run_traced(question):
    """Same loop as agent.py, but returns the full trace, not just the answer."""
    messages = [{"role": "user", "content": question}]
    trace = []
    final_text = ""

    while len(trace) < MAX_TOOL_CALLS:
        response = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            tool_choice={"type": "auto"},
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            final_text = "".join(b.text for b in response.content if b.type == "text")
            return {"trace": trace, "final_answer": final_text, "hit_call_limit": False}

        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = TOOL_FUNCTIONS.get(block.name)
                try:
                    result = fn(**block.input) if fn else {"error": f"Unknown tool: {block.name}"}
                except Exception as e:
                    result = {"error": f"Tool execution failed: {e}"}

                trace.append({
                    "tool": block.name,
                    "input": block.input,
                    "result_summary": summarize_result(result),
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

        messages.append({"role": "user", "content": tool_results})

    return {
        "trace": trace,
        "final_answer": "(no final answer: hit the tool-call limit)",
        "hit_call_limit": True,
    }


def main():
    all_results = []

    for case in TEST_CASES:
        for run in range(1, RUNS_PER_QUESTION + 1):
            print("=" * 70)
            print(f"TEST {case['id']} (run {run}): {case['question']}")
            print(f"Probes:   {case['probes']}")
            print(f"Expected: {case['expected']}\n")

            outcome = run_traced(case["question"])

            print("\nACTUAL TOOL SEQUENCE:")
            if outcome["trace"]:
                for i, step in enumerate(outcome["trace"], 1):
                    print(f"  {i}. {step['tool']}({step['input']}) -> {step['result_summary']}")
            else:
                print("  (no tool calls)")

            print(f"\nFINAL ANSWER:\n{outcome['final_answer']}\n")

            all_results.append({**case, "run": run, **outcome})

    filename = f"eval_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"Saved full results to {filename}")


if __name__ == "__main__":
    main()
