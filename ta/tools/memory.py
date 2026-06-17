# ta/tools/memory.py
import json
from typing import Annotated

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from ta.state import TAState


@tool
def summarize_history(
    state: Annotated[dict, InjectedState],
) -> Command:
    """Summarize the current conversation history to offload context.
    Call this when you feel the conversation is getting too long or complex."""
    from ta.tools.grading import _as_text, _get_llm
    
    messages = state.get("messages", [])
    if not messages:
        return Command(update={"last_tool_result": "No history to summarize."})
        
    llm = _get_llm()
    summary = state.get("summary", "")
    
    prompt = f"Current summary: {summary}\n\nNew messages to integrate:\n"
    for m in messages[-10:]: # Summarize the last 10 messages for now
        prompt += f"{m.type}: {m.content}\n"
        
    system_msg = SystemMessage(content="You are a memory manager. Create a concise summary of the conversation so far, integrating new information into the existing summary.")
    human_msg = HumanMessage(content=prompt)
    
    new_summary = _as_text(llm.invoke([system_msg, human_msg]).content)
    
    # We return a Command that updates the summary and potentially trims messages
    # Trimming messages in LangGraph usually requires a specialized node or a specific state update logic.
    # For now, we just update the 'summary' field.
    return Command(
        update={
            "summary": new_summary,
            "last_tool_result": f"History summarized. New summary: {new_summary[:100]}..."
        }
    )
