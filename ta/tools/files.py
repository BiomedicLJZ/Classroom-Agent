# ta/tools/files.py
import json
from pathlib import Path

from langchain_core.tools import tool


@tool
def write_text_file(file_path: str, content: str, overwrite: bool = True) -> str:
    """Create or overwrite a local plain text file.
    Supports: .py, .js, .jsx, .ts, .cpp, .md, .txt, .yaml, .html, .css.
    Useful for code examples, study guides, and rubrics.
    Set overwrite=False to refuse clobbering an existing file (protects instructor edits)."""
    try:
        path = Path(file_path)
        if path.exists() and not overwrite:
            return (
                f"REFUSED: '{path.resolve()}' already exists. Call again with "
                "overwrite=True to replace it, or write to a new path."
            )
        existed = path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        note = " (replaced existing file)" if existed else ""
        return f"SUCCESS: File saved to '{path.resolve()}'{note}"
    except Exception as e:
        return f"ERROR writing file: {e}"


@tool
def read_text_file(file_path: str) -> str:
    """Read the content of a local plain text or code file."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: File not found at '{file_path}'"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"ERROR reading file: {e}"


@tool
def write_notebook_file(file_path: str, cells_json: str, overwrite: bool = True) -> str:
    """Create a Jupyter Notebook (.ipynb) from a list of cell objects.
    cells_json: JSON array of {"type": "code"|"markdown", "content": "source string"}.
    Example: '[{"type": "markdown", "content": "# Title"}, {"type": "code", "content": "print(1)"}]'
    Set overwrite=False to refuse clobbering an existing file."""
    try:
        path = Path(file_path)
        if path.exists() and not overwrite:
            return (
                f"REFUSED: '{path.resolve()}' already exists. Call again with "
                "overwrite=True to replace it, or write to a new path."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        cells_data = json.loads(cells_json)
        
        notebook = {
            "cells": [],
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}},
            "nbformat": 4,
            "nbformat_minor": 4
        }
        
        for item in cells_data:
            cell = {
                "cell_type": item["type"],
                "metadata": {},
                "source": item["content"].splitlines(keepends=True)
            }
            if item["type"] == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
            notebook["cells"].append(cell)
            
        with path.open("w", encoding="utf-8") as f:
            json.dump(notebook, f, indent=1)
        return f"SUCCESS: Notebook saved to '{path.resolve()}'"
    except Exception as e:
        return f"ERROR writing notebook: {e}"


@tool
def read_notebook_file(file_path: str) -> str:
    """Read a Jupyter Notebook (.ipynb) and return a formatted string of its cells."""
    try:
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: File not found at '{file_path}'"
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        
        output = []
        for i, cell in enumerate(data.get("cells", [])):
            cell_type = cell.get("cell_type", "unknown")
            source = "".join(cell.get("source", []))
            output.append(f"--- [Cell {i}] ({cell_type}) ---\n{source}")
        return "\n\n".join(output)
    except Exception as e:
        return f"ERROR reading notebook: {e}"


@tool
def list_files(directory: str, pattern: str = "*") -> str:
    """List files in a directory matching a pattern."""
    try:
        path = Path(directory)
        if not path.exists():
            return f"ERROR: Directory not found at '{directory}'"
        found = sorted(str(f.resolve()) for f in path.glob(pattern) if f.is_file())
        if not found:
            return f"No files matching '{pattern}' found in '{directory}'"
        return "Found files:\n" + "\n".join(f"  - {f}" for f in found)
    except Exception as e:
        return f"ERROR listing files: {e}"
