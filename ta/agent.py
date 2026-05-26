# ta/agent.py
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent

from ta.config import Settings
from ta.state import TAState
from ta.tools import ALL_TOOLS

SYSTEM_PROMPT = """You are a Teaching Assistant (TA) agent for Google Classroom.

CAPABILITIES:
- Post announcements, assignments, and study materials to courses
- Check student submission status and fetch submitted work from Drive
- Grade submissions using YAML rubrics with NVIDIA AI analysis (code, reports, docs, diagrams)
- Post grades and feedback back to students

WORKFLOW GUIDELINES:
1. Identify the active course before performing operations. Ask for course ID if unclear.
2. DESTRUCTIVE actions (posting grades, announcements, creating assignments) automatically pause
   and ask the instructor for confirmation before executing.
3. Grading workflow: load_rubric → batch_grade_assignment → review summary → post_grade per student.
4. Use get_submission to get Drive file IDs, then get_drive_file_text to read content.
5. Show student IDs alongside names in all roster and status outputs.
"""


def build_agent(settings: Settings):
    """Build and compile the LangGraph ReAct TA agent."""
    llm = ChatNVIDIA(model=settings.nvidia_model, api_key=settings.nvidia_api_key)
    return create_react_agent(
        model=llm,
        tools=ALL_TOOLS,
        state_schema=TAState,
        prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
    )
