# ta/tools/planning.py
import json
from pathlib import Path

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from ta.config import Settings


class SyllabusAssignment(BaseModel):
    """One assignment within a syllabus week."""
    model_config = ConfigDict(extra="allow")
    title: str
    points: int | None = None
    description: str | None = None
    due: str | None = None  # optional date/datetime string


class SyllabusWeek(BaseModel):
    """One week of a course syllabus."""
    model_config = ConfigDict(extra="allow")
    week: int
    topic_name: str
    assignments: list[SyllabusAssignment] = Field(default_factory=list)
    announcements: list[str] = Field(default_factory=list)
    goals: list[str] | None = None


_SYLLABUS_ADAPTER = TypeAdapter(list[SyllabusWeek])


def _format_validation_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "(root)"
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def _get_course_path(course_name: str) -> Path:
    return Path(Settings().base_workspace_path) / course_name.replace(" ", "_")


@tool
def save_syllabus(course_name: str, syllabus_json: str) -> str:
    """Save a course syllabus to the local workspace as a JSON file.
    syllabus_json: JSON array of week objects, e.g.:
    [{"week": 1, "topic_name": "Intro", "assignments": [{"title": "HW1", "points": 10}]}]
    The input is validated against the syllabus schema (each week needs an integer
    'week' and a 'topic_name'); invalid input is rejected with what to fix.
    """
    path = _get_course_path(course_name) / "syllabus.json"
    try:
        raw = json.loads(syllabus_json)
    except json.JSONDecodeError as e:
        return f"ERROR: Invalid JSON: {e}"
    try:
        weeks = _SYLLABUS_ADAPTER.validate_python(raw)
    except ValidationError as e:
        return "ERROR: Syllabus failed validation. Fix and retry:\n" + _format_validation_errors(e)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [w.model_dump(exclude_none=True) for w in weeks]
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return f"SUCCESS: Syllabus saved ({len(weeks)} weeks) to {path.resolve()}"
    except Exception as e:
        return f"ERROR saving syllabus: {e}"


@tool
def load_syllabus(course_name: str) -> str:
    """Load the course syllabus JSON from the local workspace."""
    path = _get_course_path(course_name) / "syllabus.json"
    if not path.exists():
        return f"ERROR: Syllabus not found for course '{course_name}' at {path}"
    try:
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading syllabus: {e}"
