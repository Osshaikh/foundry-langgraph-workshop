"""Thin wrappers around the Azure Developer CLI (``azd``) for hosted agents.

Each lab keeps its agent under ``agents/<lab>/`` (``azure.yaml`` + ``src/``).
The helpers below copy that template into a per-lab working folder under
``.work/`` and drive the standard hosted-agent lifecycle from a notebook:

    init  ->  run (local)  ->  deploy  ->  invoke  ->  delete

Everything shells out to the same commands you would type in a terminal, and
each call prints the command so attendees can re-run it by hand.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .config import AGENTS_DIR, REPO_ROOT, settings

WORK_DIR = REPO_ROOT / ".work"
_SPINNER = re.compile(r"^\s*[-\\|/] |^\s*$")
_IS_WINDOWS = sys.platform.startswith("win")


def _azd() -> str:
    exe = shutil.which("azd")
    if not exe:
        raise RuntimeError("azd is not on PATH. Install it (see Setup) and restart VS Code.")
    return exe


def _clean(output: str) -> str:
    lines = [ln for ln in output.splitlines() if not _SPINNER.match(ln)]
    lines = [ln for ln in lines if "Update available" not in ln and "winget upgrade" not in ln]
    return "\n".join(lines)


def azd(*args: str, cwd: Path | str | None = None, check: bool = True, quiet: bool = False,
        timeout: int = 1800, retries: int = 2) -> str:
    """Run an ``azd`` command and return its (spinner-free) output."""
    cmd = [_azd(), *args]
    if not quiet:
        print("$ azd " + " ".join(args), flush=True)
    for attempt in range(retries + 1):
        proc = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout,
            env={
                **os.environ,
                "AZD_NO_UPDATE_CHECK": "1",
                "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill",
            },
            stdin=subprocess.DEVNULL,
        )
        out = _clean((proc.stdout or "") + (proc.stderr or ""))
        # azd extensions occasionally fail to fetch a token from the azd host; retry.
        if proc.returncode != 0 and "AzureDeveloperCLICredential" in out and attempt < retries:
            az = (
                shutil.which("az")
                or shutil.which("az.cmd")
                or r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
            )
            if az:
                subprocess.run(
                    [az, "account", "get-access-token", "--scope",
                     "https://management.azure.com/.default", "--output", "none"],
                    capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120,
                )
            time.sleep(5)
            continue
        break
    if check and proc.returncode != 0:
        raise RuntimeError(f"azd {' '.join(args)} failed (exit {proc.returncode}):\n{out[-4000:]}")
    return out


def _port_pids(port: int) -> set[int]:
    pids: set[int] = set()
    try:
        if _IS_WINDOWS:
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True,
                stdin=subprocess.DEVNULL, timeout=30,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 5 and parts[1].endswith(f":{port}") and parts[3] == "LISTENING":
                    pids.add(int(parts[4]))
        else:
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=30,
            ).stdout
            pids.update(int(p) for p in out.split())
    except Exception:
        pass
    return pids


def free_port(port: int) -> None:
    """Kill anything still listening on ``port`` (e.g. a previous local agent)."""
    for pid in _port_pids(port):
        try:
            if _IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/T", "/F"],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=30,
                )
            else:
                os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


@dataclass
class HostedAgentProject:
    """An azd project for one lab's hosted agent."""

    lab: str
    template_dir: Path
    project_dir: Path
    env_name: str
    agent_name: str
    port: int = 8088
    _proc: subprocess.Popen | None = field(default=None, repr=False)
    _log_path: Path | None = field(default=None, repr=False)

    # ── lifecycle ─────────────────────────────────────────────────────
    def env_set(self, **values: str) -> None:
        """``azd env set KEY VALUE`` for each keyword argument."""
        for key, value in values.items():
            azd("env", "set", key, str(value), cwd=self.project_dir, quiet=True)
            print(f"$ azd env set {key} {value}")

    def run_local(self, timeout: int = 600) -> str:
        """Start ``azd ai agent run`` in the background and wait until it is ready."""
        self.stop_local()
        self._log_path = self.project_dir / "local-run.log"
        log = open(self._log_path, "w", encoding="utf-8")
        args = [_azd(), "ai", "agent", "run", "--no-client", "--port", str(self.port)]
        print("$ azd " + " ".join(args[1:]), flush=True)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if _IS_WINDOWS else 0
        self._proc = subprocess.Popen(
            args, cwd=self.project_dir, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=flags, start_new_session=not _IS_WINDOWS,
            env={
                **os.environ,
                "AZD_NO_UPDATE_CHECK": "1",
                "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill",
                "PYTHONUNBUFFERED": "1",
            },
        )
        url = f"http://localhost:{self.port}"
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(f"Local agent exited early:\n{self.local_logs()[-4000:]}")
            try:
                if requests.get(f"{url}/readiness", timeout=3).status_code == 200:
                    print(f"Local agent ready on {url}")
                    return url
            except requests.RequestException:
                pass
            time.sleep(3)
        raise TimeoutError(f"Local agent not ready after {timeout}s:\n{self.local_logs()[-4000:]}")

    def local_logs(self) -> str:
        if self._log_path and self._log_path.exists():
            return _clean(self._log_path.read_text(encoding="utf-8", errors="replace"))
        return ""

    def stop_local(self) -> None:
        """Stop the local agent (and any orphaned host still bound to the port)."""
        if self._proc and self._proc.poll() is None:
            if _IS_WINDOWS:
                subprocess.run(
                    ["taskkill", "/PID", str(self._proc.pid), "/T", "/F"],
                    capture_output=True, stdin=subprocess.DEVNULL, timeout=30,
                )
            else:
                os.killpg(self._proc.pid, signal.SIGKILL)
        self._proc = None
        free_port(self.port)

    def deploy(self) -> str:
        """``azd deploy`` — package the source, upload it and wait until the version is active."""
        out = azd("deploy", "--no-prompt", cwd=self.project_dir, timeout=2400, retries=4)
        tail = "\n".join(ln for ln in out.splitlines() if "Polling agent status" not in ln)
        print(tail[-1500:])
        return out

    def invoke(self, message: str) -> str:
        """``azd ai agent invoke`` against the deployed agent."""
        out = azd("ai", "agent", "invoke", self.agent_name, message, cwd=self.project_dir)
        print(out)
        return out

    def show(self) -> str:
        out = azd("ai", "agent", "show", self.agent_name, cwd=self.project_dir)
        print(out)
        return out

    def monitor(self, tail: int = 50) -> str:
        out = azd("ai", "agent", "monitor", self.agent_name, "--tail", str(tail),
                  cwd=self.project_dir, check=False)
        print(out[-4000:])
        return out

    # ── local HTTP helpers ────────────────────────────────────────────
    def local_responses(self, input: str | list, **body) -> dict:
        """POST to the local ``/responses`` endpoint and return the JSON response."""
        payload = {"input": input, **body}
        r = requests.post(f"http://localhost:{self.port}/responses", json=payload, timeout=300)
        r.raise_for_status()
        return r.json()

    def local_invocations(self, message: str, session_id: str | None = None, **body) -> tuple[dict, str]:
        """POST to the local ``/invocations`` endpoint. Returns ``(json, session_id)``."""
        params = {"agent_session_id": session_id} if session_id else None
        headers = {"x-agent-session-id": session_id} if session_id else None
        r = requests.post(f"http://localhost:{self.port}/invocations", params=params,
                          headers=headers, json={"message": message, **body}, timeout=300)
        r.raise_for_status()
        return r.json(), r.headers.get("x-agent-session-id", session_id or "")

    def remote_invocations(self, message: str, session_id: str | None = None, **body) -> tuple[dict, str]:
        """POST to the deployed ``invocations`` protocol endpoint with Entra auth.

        The current v1 route is:
        ``{project_endpoint}/agents/{name}/endpoint/protocols/invocations?api-version=v1``.
        Foundry routes Invocations session affinity from the ``agent_session_id``
        query parameter. The ``x-agent-session-id`` header is also sent for
        containers that want to observe the same value.
        """
        from .config import AZURE_AI_SCOPE, credential, settings

        token = credential().get_token(AZURE_AI_SCOPE).token
        params = {"api-version": "v1"}
        if session_id:
            params["agent_session_id"] = session_id
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        if session_id:
            headers["x-agent-session-id"] = session_id
        url = f"{settings.project_endpoint}/agents/{self.agent_name}/endpoint/protocols/invocations"
        r = requests.post(url, params=params, headers=headers, json={"message": message, **body}, timeout=300)
        r.raise_for_status()
        return r.json(), r.headers.get("x-agent-session-id", session_id or "")


def init_agent(lab: str, *, port: int = 8088, model_deployment: str | None = None,
               fresh: bool = False, env: dict[str, str] | None = None) -> HostedAgentProject:
    """Initialise the lab's hosted agent as an azd project against YOUR Foundry project.

    Equivalent to::

        azd ai agent init --no-prompt -m agents/<lab>/azure.yaml \
            --project-id <project-resource-id> --model-deployment <model> -e <env>
    """
    template = AGENTS_DIR / lab
    manifest = template / "azure.yaml"
    if not manifest.exists():
        raise FileNotFoundError(manifest)
    name = _manifest_name(manifest)
    work = WORK_DIR / lab
    project_dir = work / name
    env_name = f"{settings.lab_prefix}-{lab}"[:60]

    if fresh and work.exists():
        shutil.rmtree(work, ignore_errors=True)
    if not (project_dir / "azure.yaml").exists():
        work.mkdir(parents=True, exist_ok=True)
        # azd stages template files with `git add`; .work/ is git-ignored by the
        # workshop repo, so give it its own repository.
        if not (WORK_DIR / ".git").exists():
            subprocess.run(
                ["git", "init", "-q", str(WORK_DIR)],
                check=True, stdin=subprocess.DEVNULL, timeout=60,
            )
        for attempt in range(3):
            try:
                azd("ai", "agent", "init", "--no-prompt", "-m", str(manifest),
                    "--project-id", settings.project_resource_id,
                    "--model-deployment", model_deployment or settings.chat_model,
                    "-e", env_name, cwd=work, retries=0, quiet=attempt > 0)
                break
            except RuntimeError:
                if attempt == 2:
                    raise
                shutil.rmtree(project_dir, ignore_errors=True)
                time.sleep(5)
    elif manifest.read_bytes() != (project_dir / "azure.yaml").read_bytes():
        shutil.copy2(manifest, project_dir / "azure.yaml")
    # Keep the working copy in sync with the (possibly edited) template source.
    _sync_sources(template / "src", project_dir / "src")
    project = HostedAgentProject(lab=lab, template_dir=template, project_dir=project_dir,
                                 env_name=env_name, agent_name=name, port=port)
    if env:
        project.env_set(**env)
    print(f"azd project ready: {project_dir}")
    return project


def _manifest_name(manifest: Path) -> str:
    import yaml

    data = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    for svc in (data.get("services") or {}).values():
        if svc.get("host") == "azure.ai.agent":
            return svc.get("name")
    return data["name"]


def _sync_sources(src: Path, dst: Path) -> None:
    ignore = shutil.ignore_patterns(".venv", "__pycache__", "*.pyc", ".env", "local-run.log")
    for item in src.rglob("*"):
        rel = item.relative_to(src)
        if any(part in (".venv", "__pycache__") for part in rel.parts):
            continue
        target = dst / rel
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif not target.exists() or item.read_bytes() != target.read_bytes():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)
    del ignore


def show_file(path: Path | str, language: str | None = None) -> None:
    """Pretty-print a source file in the notebook."""
    from IPython.display import Markdown, display

    path = Path(path)
    lang = language or {".py": "python", ".yaml": "yaml", ".json": "json"}.get(path.suffix, "")
    display(Markdown(f"**`{path.relative_to(REPO_ROOT).as_posix()}`**\n```{lang}\n"
                     f"{path.read_text(encoding='utf-8').rstrip()}\n```"))


def summarize_output(response: dict | object) -> None:
    """Print a compact view of Responses ``output`` items (tool calls, outputs, messages)."""
    items = response["output"] if isinstance(response, dict) else [i.model_dump() for i in response.output]
    for item in items:
        kind = item.get("type")
        if kind == "function_call":
            print(f"  → tool call   {item.get('name')}({item.get('arguments')})")
        elif kind == "function_call_output":
            print(f"  ← tool result {str(item.get('output'))[:200]}")
        elif kind == "message":
            text = "".join(c.get("text", "") for c in item.get("content", []))
            print(f"  💬 {text}")
        elif kind == "mcp_approval_request":
            print(f"  ⏸ approval requested: {item.get('name')} {str(item.get('arguments'))[:200]}")
        else:
            print(f"  · {kind}: {json.dumps(item)[:200]}")
