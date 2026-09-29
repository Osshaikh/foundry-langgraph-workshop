"""Replace environment-specific identifiers in saved notebook outputs with placeholders.

    uv run python scripts/scrub_outputs.py

Run automatically by scripts/validate.py after executing notebooks, so the published site never
shows your subscription id, tenant, resource names, e-mail or connection strings.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import nbformat

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from workshop.config import settings  # noqa: E402


def _az_value(*args: str) -> str:
    exe = shutil.which("az")
    if not exe:
        return ""
    try:
        return subprocess.run([exe, *args, "-o", "tsv"], capture_output=True, text=True,
                              stdin=subprocess.DEVNULL, timeout=120).stdout.strip()
    except Exception:
        return ""


def replacements() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    if settings.appinsights_connection_string:
        pairs.append((settings.appinsights_connection_string, "<appinsights-connection-string>"))
    for part in settings.appinsights_connection_string.split(";"):
        if "=" in part:
            key, value = part.split("=", 1)
            if key in {"InstrumentationKey", "ApplicationId"} and value:
                pairs.append((value, f"<appinsights-{key.lower()}>"))
    pairs += [
        (settings.subscription_id, "<subscription-id>"),
        (_az_value("account", "show", "--query", "tenantId"), "<tenant-id>"),
        (_az_value("account", "show", "--query", "user.name"), "<user@contoso.com>"),
        (_az_value("ad", "signed-in-user", "show", "--query", "id"), "<user-object-id>"),
    ]
    search_name = settings.search_endpoint.split("//", 1)[-1].split(".", 1)[0] if settings.search_endpoint else ""
    # Longest names first so an account name is replaced before a project name it contains.
    names = [
        (settings.account_name, "<foundry-account>"),
        (search_name, "<search-service>"),
        (settings.search_connection, "<search-connection>"),
        (settings.resource_group, "<resource-group>"),
    ]
    pairs += sorted(names, key=lambda p: len(p[0] or ""), reverse=True)
    pairs.append((settings.project_name, "<project>"))
    return [(old, new) for old, new in pairs if old and len(old) >= 4]


def scrub_text(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        if old == settings.project_name:
            # Only replace the project name as a whole path segment / word.
            text = re.sub(rf"(?<![\w-]){re.escape(old)}(?![\w-])", new, text)
        else:
            text = text.replace(old, new)
    return text


def scrub_notebook(path: Path, pairs) -> bool:
    nb = nbformat.read(path, as_version=4)
    changed = False
    for cell in nb.cells:
        for output in cell.get("outputs", []):
            if "text" in output:
                new = scrub_text(output["text"], pairs)
                changed |= new != output["text"]
                output["text"] = new
            for mime, value in list(output.get("data", {}).items()):
                if isinstance(value, str) and (mime.startswith("text/") or mime.endswith("json")):
                    new = scrub_text(value, pairs)
                    changed |= new != value
                    output["data"][mime] = new
            if "traceback" in output:
                output["traceback"] = [scrub_text(t, pairs) for t in output["traceback"]]
    if changed:
        nbformat.write(nb, path)
    return changed


def main() -> int:
    pairs = replacements()
    changed = [p.name for p in sorted((REPO_ROOT / "docs" / "modules").glob("*.ipynb")) if scrub_notebook(p, pairs)]
    for page in [REPO_ROOT / "docs" / "validation.md", REPO_ROOT / "validation" / "validation-report.md"]:
        if page.exists():
            text = page.read_text(encoding="utf-8")
            new = scrub_text(text, pairs)
            if new != text:
                page.write_text(new, encoding="utf-8")
                changed.append(page.name)
    print(f"Scrubbed {len(changed)} file(s): {', '.join(changed) or '-'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
