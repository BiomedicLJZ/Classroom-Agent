# ta/tools/workspace.py
import os
from pathlib import Path

from langchain_core.tools import tool

from ta.config import Settings


def _get_base_path() -> Path:
    return Path(Settings().base_workspace_path)


@tool
def setup_course_workspace(course_name: str, weeks: int = 16) -> str:
    """Create a structured directory for a course.
    Creates: Lesson_Plans, Materials, Assignments, Rubrics folders for each week."""
    base = _get_base_path() / course_name.replace(" ", "_")
    categories = ["Lesson_Plans", "Materials", "Assignments", "Rubrics"]

    try:
        for week in range(1, weeks + 1):
            week_dir = base / f"Week_{week:02d}"
            for cat in categories:
                (week_dir / cat).mkdir(parents=True, exist_ok=True)
        return f"SUCCESS: Workspace created for '{course_name}' at {base.resolve()}"
    except Exception as e:
        return f"ERROR setting up workspace: {e}"


@tool
def get_workspace_resource_path(course_name: str, week: int, category: str, filename: str) -> str:
    """Get the full local path for a specific resource in the workspace.
    category: 'Lesson_Plans' | 'Materials' | 'Assignments' | 'Rubrics'."""
    base = _get_base_path() / course_name.replace(" ", "_")
    path = base / f"Week_{week:02d}" / category / filename
    return str(path.resolve())


@tool
def list_workspace_contents(course_name: str = "") -> str:
    """List the contents of the local course workspace."""
    base = _get_base_path()
    if course_name:
        base = base / course_name.replace(" ", "_")

    if not base.exists():
        return f"Workspace '{base}' does not exist yet."

    output = [f"Workspace: {base.resolve()}"]
    for root, dirs, files in os.walk(base):
        level = Path(root).relative_to(base).parts
        indent = "  " * len(level)
        if level:
            output.append(f"{indent}📁 {level[-1]}")
        for f in files:
            output.append(f"{indent}  📄 {f}")

    return "\n".join(output)
