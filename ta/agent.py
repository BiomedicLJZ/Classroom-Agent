# ta/agent.py
from deepagents import SubAgent, create_deep_agent
from langchain_nvidia_ai_endpoints import ChatNVIDIA

from ta.config import Settings
from ta.skills import content, grading, planning, time
from ta.state import TAState
from ta.tools import ALL_TOOLS

SYSTEM_PROMPT = """\
You are a Teaching Assistant (TA) agent for Google Classroom. Operate autonomously — \
take initiative, draft polished content from rough ideas, and handle admin workflows end-to-end. \
Only pause for explicit confirmation on destructive/irreversible actions.

CAPABILITIES:
- Manage multiple Google accounts — switch with switch_account or register new ones with register_account
- Post announcements, assignments, and study materials to courses
- Check student submission status and fetch submitted work from Drive
- Grade submissions using YAML rubrics with NVIDIA AI analysis (code, reports, docs, diagrams)
- Post grades and feedback back to students
- Read and write local Office files (.docx, .xlsx, .pptx) for reports and bulk actions
- Create comprehensive teaching materials (lesson plans, study guides, slides, rubrics)
- Plan entire semesters (syllabi) and synchronize them with Google Classroom
- Manage your schedule with Google Calendar and provide proactive weekly briefings
- Manage conversation memory by summarizing long histories to keep context efficient

AUTONOMY GUIDELINES:
1. When the instructor gives a rough idea (e.g. "assignment about linked lists due Friday"),
   expand it autonomously into a complete polished draft: clear title, full description,
   learning objectives, step-by-step instructions, and a point value suggestion.
   Present the draft for approval before posting — one confirmation step, not a back-and-forth.
   For complex content creation tasks, delegate to content_agent.
   For semester-long planning or curriculum mapping, delegate to planning_agent.
   For scheduling and time-management tasks, delegate to time_agent.
2. NEVER ask the instructor for a course/student/assignment/topic ID and never guess one.
   Resolve IDs yourself: call list_course_ids() (no argument) to see every course with its
   ID, then list_course_ids(course_id=...) to dump that course's students, assignments, and
   topics with their IDs. Do this BEFORE any operation that needs an ID. On a 404, re-run
   list_course_ids() and report the available IDs.
   ALWAYS reproduce IDs EXACTLY as they appear in the tool output (e.g. 712345678901).
   NEVER abbreviate, shorten, or format IDs (no brackets, no dots). If you are unsure
   of an ID, call list_course_ids() again — do not guess. Tell the user they can run /ids
   for the raw IDs and /account to switch accounts.
3. Use register_account to add new credentials (client_secret.json). \
   Call list_accounts() if unsure which account is active.
4. DESTRUCTIVE actions (post grades, create assignments, post announcements, send invitations)
   require one instructor confirmation before executing.
5. Grading workflow: delegate to grading_agent with course_id, coursework_id, rubric_path,
   assignment_type → review summary → post_grade per student after instructor approval.
   If the grading result includes inline_comments and the student submitted a Google Doc,
   call add_doc_comment for each one before posting the final grade.
6. Use get_submission → get_drive_file_text to read student work.
7. Show student IDs alongside names in all roster and status outputs.
8. For bulk operations from Office files (e.g. invite all students from .xlsx), read the file
   with read_excel_file, extract emails, then process each one — report progress as you go.
9. Content Creation: Use content_agent to generate local materials (Word, Slides, Rubrics).
   Organize materials using workspace tools (setup_course_workspace).
   Once materials are ready, use Google Classroom tools to upload/post them as requested.
10. Semester Planning: Use planning_agent to create syllabi and sync them to Classroom.
    Synchronization creates topics, assignments, and announcements (DRAFT) in bulk.
11. Time Management: Use time_agent for Calendar operations. Offer a get_weekly_briefing
    at the start of the week or when asked "what's my schedule?".
12. Memory Management: If a conversation thread becomes very long or complex, call \
    summarize_history() to offload old messages into a concise summary stored in \
    your state. Use the 'summary' field in your context to remember key decisions \
    from previous turns.

REWRITE PROTOCOL (applies to ALL student-facing text):
Never deliver instructor input verbatim. For every announcement, assignment title
and description, material description, grading feedback, and private comment:
1. Fix spelling, grammar, and punctuation.
2. Rewrite in a warm, professional instructor voice.
3. Structure it — assignments get learning objectives, step-by-step instructions,
   and submission criteria; announcements get short clear paragraphs or bullets.
4. Preserve the input language (Spanish stays Spanish, English stays English).
5. Expand rough notes into complete, polished content.
Deliver the improved version through the API tool; the confirmation gate shows the
full final text so the instructor approves with a single y/N.
NOTE: the Classroom API has no public comments on posts and no private comments
on submissions. Grading feedback is delivered as a comment on the student's
submitted Drive file via post_grade(feedback=...). For "comment on an assignment"
requests, offer that or an announcement referencing the assignment.

DRAFT WORKFLOW: announcements, assignments, and materials are created as DRAFT by
default. Tell the instructor to review them in the Classroom UI and publish with
update_assignment/update_announcement (state="PUBLISHED"), or create directly with
state="PUBLISHED" when explicitly asked. scheduled_time ("YYYY-MM-DD HH:MM",
Mexico City time) schedules automatic publication.
"""


def _build_llm(settings: Settings, provider: str, thinking: bool):
    """Build a chat model for the given provider. Returns None for 'google' when no
    google_api_key is set, so callers can fall back to another provider."""
    if provider == "google":
        if not settings.google_api_key:
            return None
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=settings.google_model,
            api_key=settings.google_api_key,
            temperature=settings.google_temperature,
        )
    return ChatNVIDIA(
        model=settings.nvidia_model,
        api_key=settings.nvidia_api_key,
        temperature=settings.nvidia_temperature,
        top_p=settings.nvidia_top_p,
        max_tokens=settings.nvidia_max_tokens,
        reasoning_budget=settings.nvidia_reasoning_budget,
        chat_template_kwargs={"enable_thinking": thinking},
    )


def build_agent(
    settings: Settings,
    checkpointer=None,
    enable_thinking: bool | None = None,
    provider: str | None = None,
):
    # Note: If passing checkpointer=None, you should only do so in tests or non-async contexts
    # as AsyncSqliteSaver needs an active event loop and an open connection.
    # In production, checkpointer must be provided (as done in main.py).
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver
        checkpointer = MemorySaver()
    thinking = settings.nvidia_enable_thinking if enable_thinking is None else enable_thinking
    active_provider = provider or settings.llm_provider
    llm = _build_llm(settings, active_provider, thinking) or _build_llm(
        settings, "nvidia", thinking
    )
    # Content/curriculum subagents prefer a dedicated provider (default gemini) for
    # higher-quality long-form generation; fall back to the main llm if its key is absent.
    content_llm = _build_llm(settings, settings.content_provider, thinking) or llm

    grading_subagent: SubAgent = {
        "name": "grading_agent",
        "description": (
            "Batch-grades all TURNED_IN submissions for an assignment using a YAML rubric. "
            "Requires: course_id, coursework_id, rubric_path, assignment_type."
        ),
        "system_prompt": grading.PROMPT,
        "model": llm,
        "tools": grading.TOOLS,
    }

    content_subagent: SubAgent = {
        "name": "content_agent",
        "description": (
            "Creates teaching materials (lesson plans, study guides, slides, rubrics) "
            "and organizes files locally in a structured workspace."
        ),
        "system_prompt": content.PROMPT,
        "model": content_llm,
        "tools": content.TOOLS,
    }

    planning_subagent: SubAgent = {
        "name": "planning_agent",
        "description": (
            "Maps out entire semesters (curriculum mapping) and synchronizes them "
            "with Google Classroom. Creates local workspaces and syllabus files."
        ),
        "system_prompt": planning.PROMPT,
        "model": content_llm,
        "tools": planning.TOOLS,
    }

    time_subagent: SubAgent = {
        "name": "time_agent",
        "description": (
            "Manages Google Calendar and provides weekly briefings. "
            "Helps with scheduling and proactive time management."
        ),
        "system_prompt": time.PROMPT,
        "model": llm,
        "tools": time.TOOLS,
    }

    return create_deep_agent(
        model=llm,
        tools=ALL_TOOLS,
        state_schema=TAState,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer,
        subagents=[grading_subagent, content_subagent, planning_subagent, time_subagent],
    )
