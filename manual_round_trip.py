"""
Manual completion of one full tool-use round trip.

Deliberately manual, not automated yet: we take Claude's tool request from
the previous test, execute the REAL function ourselves, and send the
result back by hand. This builds real understanding of the mechanism
before we let code handle it automatically in the next step.

This also lets us directly observe how Claude handles a real, honest
limitation we already know about: our complaint_type filter requires an
exact match, and Claude's natural guess ("Noise") won't exactly match
NYC's real category ("Noise - Residential") - so we expect this specific
call to return zero results, and want to see how Claude responds to that.
"""

import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv
from tool_schemas import TOOL_311_COMPLAINTS
from tools_311 import get_311_complaints

load_dotenv()

client = Anthropic()

# Step 1: send the question, same as before
messages = [
    {"role": "user", "content": "Is it noisy in Brooklyn right now?"}
]

first_response = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    tools=[TOOL_311_COMPLAINTS],
    tool_choice={"type": "auto"},
    messages=messages
)

print("Step 1 - Claude's first response:")
print(f"  Stop reason: {first_response.stop_reason}")

# Step 2: find the tool_use block and actually execute the real function
tool_use_block = None
for block in first_response.content:
    if block.type == "tool_use":
        tool_use_block = block
        print(f"  Claude wants to call: {block.name} with {block.input}")

if tool_use_block:
    # Actually execute our real, tested function with Claude's chosen arguments
    real_result = get_311_complaints(
        location=tool_use_block.input.get("location"),
        complaint_type=tool_use_block.input.get("complaint_type"),
        time_period_days=tool_use_block.input.get("time_period_days", 30)
    )

    print(f"\nStep 2 - Real function executed. Found {len(real_result)} results.")

    # Step 3: send the real result back to Claude, continuing the conversation
    # We have to include Claude's own previous message, then our tool_result
    messages.append({"role": "assistant", "content": first_response.content})
    messages.append({
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": tool_use_block.id,
                "content": json.dumps(real_result)
            }
        ]
    })

    final_response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        tools=[TOOL_311_COMPLAINTS],
        tool_choice={"type": "auto"},
        messages=messages
    )

    print(f"\nStep 3 - Claude's final response after seeing the real result:")
    print(f"  Stop reason: {final_response.stop_reason}")
    for block in final_response.content:
        if block.type == "text":
            print(f"  Text: {block.text}")
else:
    print("Claude did not request a tool this time.")
