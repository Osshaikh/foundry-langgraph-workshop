"""Safe CLI helpers for notebook cells.

Jupyter validation runs with a live kernel stdin. Some CLIs wait forever if
they inherit it, so helpers here always close stdin and set a timeout.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any


def _exe(name: str) -> str:
    found = shutil.which(name) or shutil.which(f"{name}.cmd")
    if found:
        return found
    if name == "az":
        return r"C:\Program Files\Microsoft SDKs\Azure\CLI2\wbin\az.cmd"
    raise FileNotFoundError(name)


def az(*args: str, json_out: bool = True, timeout: int = 300) -> Any:
    """Run Azure CLI with stdin closed and a bounded timeout.

    When ``json_out`` is true, ``-o json`` is appended unless an output option
    is already present, and the parsed JSON result is returned. Otherwise the
    combined stdout text is returned.
    """
    cmd = [_exe("az"), *args]
    if json_out and "-o" not in args and "--output" not in args:
        cmd += ["-o", "json"]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdin=subprocess.DEVNULL,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "").strip())
    output = (proc.stdout or "").strip()
    return json.loads(output) if json_out and output else output
