"""Remove what the labs created in your Foundry project (keeps models and shared resources).

    uv run python scripts/cleanup.py            # dry run: list what would be deleted
    uv run python scripts/cleanup.py --yes      # delete

Deletes: hosted agents, toolboxes and memory stores whose names start with LAB_PREFIX (default "lgws"),
and Azure AI Search indexes with that prefix. Fine-tuned model deployments are listed but only deleted
with --include-finetuned (they bill hourly while deployed).

To remove EVERYTHING (resource group), use scripts/teardown.ps1 instead.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from workshop.config import credential, project_client, settings  # noqa: E402


def _names(iterable, attr="name"):
    out = []
    try:
        for item in iterable:
            if isinstance(item, str):
                out.append(item)
                continue
            name = getattr(item, attr, None) or (item.get(attr) if isinstance(item, dict) else None)
            if name:
                out.append(name)
    except Exception as exc:  # feature not available in this project/SDK
        print(f"  (skipped: {type(exc).__name__}: {exc})")
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--yes", action="store_true", help="actually delete")
    parser.add_argument("--include-finetuned", action="store_true", help="also delete *-ft model deployments")
    args = parser.parse_args()
    prefix = settings.lab_prefix
    project = project_client()
    plan: list[tuple[str, str, callable]] = []

    for name in _names(project.agents.list()):
        if name.startswith(prefix):
            plan.append(("agent", name, lambda n=name: project.agents.delete(agent_name=n)))

    toolboxes = getattr(project, "toolboxes", None)
    if toolboxes is not None:
        for name in _names(toolboxes.list()):
            if name.startswith(prefix):
                plan.append(("toolbox", name, lambda n=name: toolboxes.delete(name=n)))

    stores = getattr(project, "memory_stores", None)
    if stores is not None:
        for name in _names(stores.list()):
            if name.startswith(prefix):
                plan.append(("memory store", name, lambda n=name: stores.delete(name=n)))

    if settings.search_endpoint:
        from azure.search.documents.indexes import SearchIndexClient

        sic = SearchIndexClient(settings.search_endpoint, credential())
        for name in _names(sic.list_index_names()):
            if name.startswith(prefix):
                plan.append(("search index", name, lambda n=name: sic.delete_index(n)))

    if args.include_finetuned:
        for name in _names(project.deployments.list()):
            if name.startswith("gpt-4.1-mini-lgws") or name.endswith("-ft"):
                plan.append(("model deployment", name, lambda n=name: subprocess.run(
                    [shutil.which("az") or "az", "cognitiveservices", "account", "deployment", "delete",
                     "-g", settings.resource_group, "-n", settings.account_name, "--deployment-name", n],
                    check=True, stdin=subprocess.DEVNULL)))

    if not plan:
        print("Nothing to clean up.")
        return 0
    for kind, name, _ in plan:
        print(f"{'DELETE' if args.yes else 'would delete'} {kind:16} {name}")
    if not args.yes:
        print("\nDry run. Re-run with --yes to delete.")
        return 0
    failures = 0
    for kind, name, action in plan:
        try:
            action()
        except Exception as exc:
            failures += 1
            print(f"  failed {kind} {name}: {exc}")
    print("Done." if not failures else f"Done with {failures} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
