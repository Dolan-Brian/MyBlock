"""
MyBlock's core agent loop.

This is the real, reusable mechanism: given any question, Claude decides
which of the five tools (if any) to call, we execute the real function,
send the result back, and repeat - automatically, for as many rounds as
Claude genuinely needs - until it has enough information to give a final
answer.

This is the actual agentic decision-making at the heart of the project:
nothing here hardcodes which tool gets called or in what order. That's
entirely Claude's live decision, based on the specific question and what
it learns from each tool result along the way.
"""

import json
from anthropic import Anthropic
from dotenv import load_dotenv

from tool_schemas import ALL_TOOLS
from tools_311 import get_311_complaints
from tools_trend import get_historical_trend
from tools_parking import get_parking_violations
from tools_permits import get_building_permits
from tools_traffic import get_traffic_speeds

load_dotenv()

client = Anthropic()

# Added after the first eval run (see EVAL_SET.md) found four recurring
# failure modes: stating facts that never came from a tool (Test 7),
# presenting borough-wide data as if it were neighborhood-specific
# (Test 1), treating an empty or zero result as evidence that nothing is
# happening rather than as missing data (Tests 2, 5), and treating one
# data point as if it showed a trend (Test 2).
#
# Rule 2 below was rewritten after a second eval run (see EVAL_SET.md,
# "An Unresolved Tradeoff") showed the original version overcorrected:
# it fixed the granularity problem by making the agent ask permission
# before calling a tool at all, which is safer but less useful than the
# baseline's behavior of calling the tool and filtering the real
# response down to what's relevant. Rule 6 was added for the same
# reason - the rubric had no way to penalize an answer for being overly
# cautious, only for being wrong.
#
# Rule 7 (new) was added after running the same nine questions three
# times each (see EVAL_SET.md, "Third Round") showed Test 5 regressing
# in one run out of three: the answer called traffic data "real-time,"
# gave no timestamp, and answered a 3am question from data collected
# hours later with no acknowledgment of the gap. Rule 5 already covered
# uncertainty about whether a *location* was matched correctly; it said
# nothing specific about *time*, which is likely why that case was
# handled inconsistently across otherwise-identical runs.
SYSTEM_PROMPT = """You are a research assistant with access to real NYC \
civic data tools. Follow these rules strictly:

1. State only facts that came from a tool's returned data in this \
conversation. Never state a specific address, zip code, distance, or \
landmark detail unless it appeared in a tool result. If you want to \
add general knowledge, label it clearly as such, separate from the data.

2. Every tool here reports data at the borough level, not at the \
neighborhood or address level. When a question names a neighborhood or \
landmark, call the relevant tool for its borough and use the returned \
data - do not ask permission first. If individual records in the result \
include an address, you may use those to narrow your answer to what's \
actually relevant. State plainly, as part of your answer, that the \
underlying data is borough-wide.

3. An empty or zero result is missing data, not a finding. Never \
describe it as calm, quiet, safe, or good. Say plainly that no data \
was available for that query and time window.

4. A single number or a single time snapshot is not a trend. Only \
describe something as improving, worsening, or changing over time if \
the data itself came from a tool built to compare two time periods.

5. If you are not confident a tool understood the location as intended \
(for example, a neighborhood name rather than a borough), say so \
explicitly rather than presenting the result as if it matched the \
user's question exactly.

6. If a question asks about a specific time (a particular hour, "right \
now", "lately"), and a tool returns data with its own timestamp, state \
that timestamp and whether it could plausibly cover the time asked \
about. Never call data "real-time" or "current" without giving the \
actual timestamp. If the two don't clearly match, say so explicitly \
rather than answering as if they do.

7. Always attempt the most useful available tool call before answering. \
Disclosing a limitation is not a substitute for using the data you have \
access to. Only decline to look something up, or ask a clarifying \
question first, when no available tool could plausibly help at all."""

# Maps each tool's name (as Claude will refer to it) to the real Python
# function that actually executes it. This is the bridge between what
# Claude requests and what our own code does.
TOOL_FUNCTIONS = {
    "get_311_complaints": get_311_complaints,
    "get_historical_trend": get_historical_trend,
    "get_parking_violations": get_parking_violations,
    "get_building_permits": get_building_permits,
    "get_traffic_speeds": get_traffic_speeds,
}

# A hard safety and cost-control limit - prevents a genuinely unbounded
# loop if something ever goes wrong. Set to 5, matching our five real
# tools - a reasonable ceiling assuming a question might need each tool
# called once, without allowing unlimited, runaway calls.
MAX_TOOL_CALLS = 5


def run_agent(user_question):
    """
    Runs the full agentic loop for a single user question. Returns the
    final text answer, and prints each step along the way so the actual
    tool-call sequence is visible, not hidden.
    """
    messages = [{"role": "user", "content": user_question}]
    tool_call_count = 0

    print(f"Question: {user_question}\n")

    while tool_call_count < MAX_TOOL_CALLS:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            tools=ALL_TOOLS,
            tool_choice={"type": "auto"},
            messages=messages
        )

        # If Claude is done reasoning and ready to answer, stop the loop
        if response.stop_reason != "tool_use":
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
            return final_text

        # Otherwise, Claude wants at least one tool - find and execute it
        messages.append({"role": "assistant", "content": response.content})

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                tool_call_count += 1
                print(f"  [Tool call {tool_call_count}] {block.name}({block.input})")

                real_function = TOOL_FUNCTIONS.get(block.name)
                if real_function:
                    try:
                        result = real_function(**block.input)
                    except Exception as e:
                        result = {"error": f"Tool execution failed: {str(e)}"}
                else:
                    result = {"error": f"Unknown tool: {block.name}"}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str)
                })

        messages.append({"role": "user", "content": tool_results})

    # If we somehow hit the safety limit without a final answer
    return "I wasn't able to fully answer this within a reasonable number of tool calls - the question may be too broad, or may need to be more specific."


if __name__ == "__main__":
    # A few genuinely varied test questions to start with
    answer = run_agent("Is it noisy in Brooklyn right now?")
    print(f"\nFinal answer:\n{answer}")
