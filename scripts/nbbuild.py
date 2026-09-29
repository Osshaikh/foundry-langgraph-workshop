"""Tiny notebook builder shared by the ``scripts/gen_*.py`` lab generators.

Generators are the source of truth; notebooks are regenerated from them, then
executed by ``scripts/validate.py`` so the saved outputs are real.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

REPO_ROOT = Path(__file__).resolve().parents[1]

BOOTSTRAP = """\
# ── Workshop bootstrap (same in every lab) ─────────────────────────────
import sys, pathlib
ROOT = next(p for p in [pathlib.Path.cwd(), *pathlib.Path.cwd().parents] if (p / "pyproject.toml").exists())
sys.path.insert(0, str(ROOT))
from workshop.config import settings
print("Project :", settings.project_endpoint)
print("Model   :", settings.chat_model)"""


class Notebook:
    def __init__(self, title: str, subtitle: str = "", minutes: int | None = None) -> None:
        self.nb = new_notebook()
        self.nb.metadata["kernelspec"] = {
            "name": "foundry-langgraph-workshop",
            "display_name": "Foundry LangGraph Workshop",
            "language": "python",
        }
        self.nb.metadata["language_info"] = {"name": "python"}
        header = f"# {title}"
        if subtitle:
            header += f"\n\n> {subtitle}"
        if minutes:
            header += f"\n\n⏱️ **Time:** ~{minutes} minutes"
        self.md(header)

    def md(self, text: str) -> "Notebook":
        self.nb.cells.append(new_markdown_cell(textwrap.dedent(text).strip()))
        return self

    def code(self, source: str, *, tags: list[str] | None = None) -> "Notebook":
        cell = new_code_cell(textwrap.dedent(source).strip())
        if tags:
            cell.metadata["tags"] = tags
        self.nb.cells.append(cell)
        return self

    def bootstrap(self) -> "Notebook":
        return self.code(BOOTSTRAP)

    def your_turn(self, text: str, starter: str | None = None) -> "Notebook":
        self.md("## 🧪 Your turn\n\n" + textwrap.dedent(text).strip())
        if starter:
            self.code(starter, tags=["your-turn"])
        return self

    def save(self, rel_path: str) -> Path:
        path = REPO_ROOT / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        nbformat.write(self.nb, path)
        print(f"wrote {path.relative_to(REPO_ROOT).as_posix()}")
        return path
