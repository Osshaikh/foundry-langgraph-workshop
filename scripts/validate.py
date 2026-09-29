"""Execute lab notebooks top-to-bottom against your Foundry project.

    python scripts/validate.py                 # all labs
    python scripts/validate.py 01 02           # selected labs (prefix match)

Executed outputs are saved back into the notebooks (so the site shows real
results) and a summary is written to validation/validation-report.md.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
import time
import traceback
from pathlib import Path

import nbformat
from nbclient import NotebookClient

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES = REPO_ROOT / "docs" / "modules"
REPORT = REPO_ROOT / "validation" / "validation-report.md"
KERNEL = "foundry-langgraph-workshop"


def run(nb_path: Path, timeout: int) -> tuple[str, float, str]:
    nb = nbformat.read(nb_path, as_version=4)
    start = time.time()
    client = NotebookClient(nb, timeout=timeout, kernel_name=KERNEL,
                            resources={"metadata": {"path": str(nb_path.parent)}})
    try:
        client.execute()
        status, note = "PASS", ""
    except Exception as exc:
        status, note = "FAIL", str(exc).strip().splitlines()[-1][:300]
        (REPO_ROOT / "validation").mkdir(exist_ok=True)
        (REPO_ROOT / "validation" / f"{nb_path.stem}.error.txt").write_text(
            f"{exc}\n\n{traceback.format_exc()}", encoding="utf-8")
    finally:
        nbformat.write(nb, nb_path)
    return status, time.time() - start, note


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    selected = argv[1:]
    notebooks = sorted(MODULES.glob("*.ipynb"))
    if selected:
        notebooks = [n for n in notebooks if any(n.name.startswith(s) for s in selected)]
    rows = []
    for nb in notebooks:
        print(f"▶ {nb.name}", flush=True)
        status, secs, note = run(nb, timeout=3600)
        print(f"  {status} in {secs:.0f}s {note}", flush=True)
        rows.append((nb.name, status, secs, note))

    REPORT.parent.mkdir(exist_ok=True)
    existing: dict[str, str] = {}
    if REPORT.exists():
        for line in REPORT.read_text(encoding="utf-8").splitlines():
            if line.startswith("| ") and ".ipynb" in line:
                existing[line.strip("|").split("|")[0].strip()] = line
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    for name, status, secs, note in rows:
        existing[name] = f"| {name} | {status} | {secs:.0f}s | {stamp} | {note} |"
    body = ["# Validation report", "",
            "Every lab notebook executed top-to-bottom against a live Foundry project.", "",
            "| Notebook | Result | Duration | Run at | Notes |", "|---|---|---|---|---|",
            *[existing[k] for k in sorted(existing)]]
    notes = REPO_ROOT / "validation" / "notes.md"
    if notes.exists():
        body += ["", notes.read_text(encoding="utf-8").strip()]
    REPORT.write_text("\n".join(body) + "\n", encoding="utf-8")
    site_page = REPO_ROOT / "docs" / "validation.md"
    site_page.write_text(
        "\n".join(body[:4]
                  + ["Regenerate with `uv run python scripts/validate.py` against your own project.", ""]
                  + body[4:]) + "\n",
        encoding="utf-8",
    )
    failed = [r for r in rows if r[1] != "PASS"]
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "scrub_outputs.py")], check=False,
                   stdin=subprocess.DEVNULL)
    print(f"\n{len(rows) - len(failed)}/{len(rows)} passed -> {REPORT.relative_to(REPO_ROOT)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
