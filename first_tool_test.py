"""
First real tool-use test for MyBlock.

Deliberately minimal: one simple question, one tool available. The goal
right now is just to SEE Claude correctly request a tool - we are not yet
executing the real function or completing the round trip. That comes next,
once we've confirmed this first, foundational step works.
"""

import os
import json
from anthropic import Anthropic
from dotenv import load_dotenv
from tool_schemas import TOOL_311_COMPLAINTS

load_dotenv()

client = Anthropic()  # reads ANTHROPIC_API_KEY from your environment automatically

message = client.messages.create(
    model="claude-haiku-4-5-20251001",
    max_tokens=1024,
    tools=[TOOL_311_COMPLAINTS],
    tool_choice={"type": "auto"},
    messages=[
        {"role": "user", "content": "Is it noisy in Brooklyn right now?"}
    ]
)

print("Full response object:")
print(message)

print("\n\nStop reason:", message.stop_reason)

print("\nContent blocks:")
for block in message.content:
    print(f"  Type: {block.type}")
    if block.type == "tool_use":
        print(f"  Tool name: {block.name}")
        print(f"  Tool input: {json.dumps(block.input, indent=2)}")
    elif block.type == "text":
        print(f"  Text: {block.text}")
