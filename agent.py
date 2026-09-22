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
