"""Utilities for M14 fine-tuning lab.

The functions are intentionally notebook-friendly: they write durable state under
``validation/`` so a long-running fine-tuning job can be submitted once and later
reattached by rerunning the notebook or ``scripts/validate.py 14``.
"""

from __future__ import annotations

import json
import os
import random
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

import requests

from .config import REPO_ROOT, credential, settings

SYSTEM_PROMPT = (
    "You are Contoso Outdoor Support. Reply only as valid JSON with keys: "
    "reply, tone, next_action, discount_code. Tone must be warm, concise, and "
    "policy-safe. Use discount_code null unless the customer qualifies for a "
    "goodwill discount."
)

REQUIRED_KEYS = {"reply", "tone", "next_action", "discount_code"}
DONE_STATUSES = {"succeeded", "failed", "cancelled", "canceled"}
SUCCESS_STATUSES = {"succeeded"}


def state_path(root: Path = REPO_ROOT) -> Path:
    return root / "validation" / "m14-ft-job.json"


def data_dir(root: Path = REPO_ROOT) -> Path:
    return root / "validation" / "m14-ft-data"


def load_state(root: Path = REPO_ROOT) -> dict[str, Any]:
    path = state_path(root)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict[str, Any], root: Path = REPO_ROOT) -> dict[str, Any]:
    path = state_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    return state


def _extract_text(response: Any) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return str(text)
    if hasattr(response, "choices"):
        return response.choices[0].message.content or ""
    return str(response)


def _extract_json(text: str) -> Any:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def _deterministic_examples(total: int) -> list[dict[str, Any]]:
    products = ["TrailMaster tent", "SummitLite backpack", "RidgeRun boots", "CampChef stove", "StormGuard jacket"]
    issues = [
        "arrived two days late before a camping trip",
        "zipper failed during the first weekend",
        "color was different from the product page",
        "size guide led to the wrong fit",
        "gift order missed the birthday delivery date",
        "loyalty customer found a lower competitor price",
        "replacement part is out of stock",
    ]
    actions = [
        ("refund", "Process a partial refund and apologize for the inconvenience.", None),
        ("replacement", "Offer a prepaid return label and expedited replacement.", None),
        ("discount", "Offer a goodwill discount for the next order.", "OUTDOOR10"),
        ("escalate", "Escalate to a specialist and give a clear follow-up window.", None),
    ]
    examples: list[dict[str, Any]] = []
    for i in range(total):
        product = products[i % len(products)]
        issue = issues[i % len(issues)]
        action, next_action, code = actions[i % len(actions)]
        prompt = (
            f"Customer case CO-{1000+i}: The customer bought a {product}; it {issue}. "
            f"They ask for a {action}. Write the support reply."
        )
        answer = {
            "reply": (
                f"Thanks for contacting Contoso Outdoor. I am sorry the {product} {issue}. "
                f"We can help with a {action} while keeping the resolution aligned to our support policy."
            ),
            "tone": "warm, concise, policy-safe",
            "next_action": next_action,
            "discount_code": code,
        }
        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
            ]
        })
    random.Random(13).shuffle(examples)
    return examples


def generate_examples_with_teacher(client: Any, total: int = 75, batch_size: int = 25) -> tuple[list[dict[str, Any]], str]:
    """Ask the teacher for JSONL-style examples; fall back to deterministic data."""
    examples: list[dict[str, Any]] = []
    errors: list[str] = []
    for batch_index, offset in enumerate(range(0, total, batch_size), start=1):
        count = min(batch_size, total - offset)
        prompt = f"""
Generate {count} supervised fine-tuning examples for this narrow task.
Task: Contoso Outdoor customer support replies in a fixed JSON style.
Return ONLY a JSON array. Each item must be {{"messages": [...]}}. The messages must be:
1. system: exactly {SYSTEM_PROMPT!r}
2. user: a realistic customer support case about outdoor gear refunds, replacements, shipping, warranty, discounts, or loyalty concerns
3. assistant: a JSON string with keys reply, tone, next_action, discount_code
Make examples varied and safe. Batch {batch_index}; start case numbers at {offset + 1}.
""".strip()
        try:
            response = client.responses.create(model=settings.reasoning_model, input=prompt)
            data = _extract_json(_extract_text(response))
            for item in data:
                if _valid_training_item(item):
                    examples.append(item)
        except Exception as exc:  # keep class notebooks resilient
            errors.append(f"batch {batch_index}: {type(exc).__name__}: {exc}")
    if len(examples) >= total:
        return examples[:total], "teacher"
    fallback = _deterministic_examples(total)
    source = "deterministic fallback"
    if errors:
        source += "; teacher errors: " + " | ".join(errors)[:1000]
    return fallback, source


def _valid_training_item(item: Any) -> bool:
    if not isinstance(item, dict) or "messages" not in item:
        return False
    messages = item["messages"]
    if not isinstance(messages, list) or len(messages) < 3:
        return False
    roles = [m.get("role") for m in messages if isinstance(m, dict)]
    if "user" not in roles or roles[-1] != "assistant":
        return False
    return all(isinstance(m.get("content"), str) and m["content"].strip() for m in messages)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def ensure_dataset(client: Any, root: Path = REPO_ROOT, train_count: int = 60, val_count: int = 15) -> dict[str, Any]:
    out_dir = data_dir(root)
    train_path = out_dir / "train.jsonl"
    val_path = out_dir / "validation.jsonl"
    state = load_state(root)
    if train_path.exists() and val_path.exists():
        return {"train_path": str(train_path), "validation_path": str(val_path), "source": state.get("dataset_source", "existing")}
    examples, source = generate_examples_with_teacher(client, train_count + val_count)
    write_jsonl(train_path, examples[:train_count])
    write_jsonl(val_path, examples[train_count:train_count + val_count])
    state.update({"dataset_source": source, "train_path": str(train_path), "validation_path": str(val_path)})
    save_state(state, root)
    return {"train_path": str(train_path), "validation_path": str(val_path), "source": source}


def score_reply(text: str) -> dict[str, Any]:
    try:
        obj = _extract_json(text)
    except Exception as exc:
        return {"score": 0.0, "valid_json": False, "error": str(exc)[:120]}
    missing = sorted(REQUIRED_KEYS - set(obj)) if isinstance(obj, dict) else sorted(REQUIRED_KEYS)
    reply = str(obj.get("reply", "")) if isinstance(obj, dict) else ""
    tone = str(obj.get("tone", "")) if isinstance(obj, dict) else ""
    score = 0.0
    score += 0.45 if isinstance(obj, dict) and not missing else 0.0
    score += 0.20 if "warm" in tone.lower() or "concise" in tone.lower() or "policy" in tone.lower() else 0.0
    score += 0.20 if 40 <= len(reply) <= 500 else 0.0
    score += 0.15 if "Contoso" in reply or "Outdoor" in reply else 0.0
    return {"score": round(score, 2), "valid_json": isinstance(obj, dict), "missing": missing, "object": obj}


def call_support_model(client: Any, deployment: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model=deployment,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )
    return _extract_text(response)


def evaluate_deployment(client: Any, deployment: str, validation_path: str | Path, limit: int = 15) -> dict[str, Any]:
    rows = read_jsonl(Path(validation_path))[:limit]
    results = []
    cooldown = 65 if deployment.endswith("lgws-ft") else 0
    for row in rows:
        user_prompt = next(m["content"] for m in row["messages"] if m["role"] == "user")
        try:
            last_exc: Exception | None = None
            text = ""
            for attempt in range(3):
                try:
                    text = call_support_model(client, deployment, user_prompt)
                    break
                except Exception as exc:
                    last_exc = exc
                    message = str(exc)
                    if "rate" in message.lower() or "DeploymentNotReady" in message or "dependent service" in message.lower():
                        time.sleep(65)
                        continue
                    raise
            if not text and last_exc:
                raise last_exc
            scored = score_reply(text)
            results.append({"prompt": user_prompt, "output": text, **scored})
        except Exception as exc:
            results.append({"prompt": user_prompt, "output": "", "score": 0.0, "valid_json": False, "error": f"{type(exc).__name__}: {exc}"})
        if cooldown and len(results) < len(rows):
            time.sleep(cooldown)
    avg = sum(r["score"] for r in results) / max(len(results), 1)
    return {"deployment": deployment, "average_score": round(avg, 3), "results": results}


def _wait_for_files(client: Any, file_ids: list[str], timeout: int = 600) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        statuses = [getattr(client.files.retrieve(fid), "status", "") for fid in file_ids]
        if all(s in {"processed", "uploaded"} for s in statuses):
            return
        time.sleep(10)
    raise TimeoutError(f"Files not processed after {timeout}s: {file_ids}")


def _model_candidates() -> list[str]:
    base = settings.finetune_base_model
    candidates = []
    if base == "gpt-4.1-mini":
        candidates.append("gpt-4.1-mini-2025-04-14")
    candidates.extend([base, "gpt-4.1-nano-2025-04-14", "gpt-4o-mini-2024-07-18"])
    return list(dict.fromkeys(candidates))


def submit_or_attach_job(client: Any, root: Path = REPO_ROOT) -> dict[str, Any]:
    state = load_state(root)
    env_job = os.environ.get("LGWS_FT_JOB_ID")
    if env_job and state.get("job_id") != env_job:
        state["job_id"] = env_job
        state["attached_from_env"] = True
        save_state(state, root)
    if state.get("job_id"):
        return state

    dataset = ensure_dataset(client, root)
    train_path = Path(dataset["train_path"])
    val_path = Path(dataset["validation_path"])
    with train_path.open("rb") as f:
        train_file = client.files.create(file=f, purpose="fine-tune")
    with val_path.open("rb") as f:
        val_file = client.files.create(file=f, purpose="fine-tune")
    state.update({"training_file_id": train_file.id, "validation_file_id": val_file.id})
    save_state(state, root)
    _wait_for_files(client, [train_file.id, val_file.id])

    errors: list[str] = []
    for model in _model_candidates():
        for training_type in ("globalStandard", "developer", None):
            kwargs: dict[str, Any] = {
                "model": model,
                "training_file": train_file.id,
                "validation_file": val_file.id,
                "suffix": "lgws",
                "method": {"type": "supervised"},
                "hyperparameters": {"n_epochs": 2, "learning_rate_multiplier": 0.8},
            }
            if training_type:
                kwargs["extra_body"] = {"trainingType": training_type}
            try:
                job = client.fine_tuning.jobs.create(**kwargs)
                state.update({
                    "job_id": job.id,
                    "job_status": getattr(job, "status", "unknown"),
                    "job_model": model,
                    "training_type": training_type or "default",
                    "submitted_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "submission_errors": errors,
                })
                return save_state(state, root)
            except Exception as exc:
                errors.append(f"{model}/{training_type or 'default'}: {type(exc).__name__}: {str(exc)[:700]}")
    state.update({"job_status": "unavailable", "submission_errors": errors})
    return save_state(state, root)


def refresh_job(client: Any, root: Path = REPO_ROOT) -> dict[str, Any]:
    state = load_state(root)
    if not state.get("job_id"):
        return state
    job = client.fine_tuning.jobs.retrieve(state["job_id"])
    state.update({
        "job_status": getattr(job, "status", "unknown"),
        "fine_tuned_model": getattr(job, "fine_tuned_model", None),
        "finished_at": getattr(job, "finished_at", None),
        "trained_tokens": getattr(job, "trained_tokens", None),
    })
    return save_state(state, root)


def wait_for_job(client: Any, root: Path = REPO_ROOT, max_wait_seconds: int = 3300, interval_seconds: int = 60) -> dict[str, Any]:
    start = time.time()
    state = refresh_job(client, root)
    while state.get("job_status") not in DONE_STATUSES and time.time() - start < max_wait_seconds:
        print(f"job {state.get('job_id')} status={state.get('job_status')} elapsed={int(time.time()-start)}s")
        time.sleep(interval_seconds)
        state = refresh_job(client, root)
    state["last_poll_duration_seconds"] = int(time.time() - start)
    return save_state(state, root)


def _run_az(args: list[str], timeout: int = 900) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "AZURE_DEV_USER_AGENT": "microsoft_foundry_skill"}
    return subprocess.run(
        [shutil.which("az") or "az", *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=env,
        stdin=subprocess.DEVNULL,
    )


def _deploy_arm_rest(model_name: str, deployment_name: str, sku_name: str, capacity: int = 1) -> dict[str, Any]:
    token = credential().get_token("https://management.azure.com/.default").token
    url = (
        f"https://management.azure.com/subscriptions/{settings.subscription_id}"
        f"/resourceGroups/{settings.resource_group}"
        f"/providers/Microsoft.CognitiveServices/accounts/{settings.account_name}"
        f"/deployments/{deployment_name}?api-version=2024-10-01"
    )
    body = {
        "sku": {"name": sku_name, "capacity": capacity},
        "properties": {
            "model": {
                "format": "OpenAI",
                "name": model_name,
                "version": "1",
            }
        },
    }
    response = requests.put(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
        timeout=1200,
    )
    if response.status_code not in (200, 201, 202):
        raise RuntimeError(f"ARM {response.status_code}: {response.text[:1500]}")
    return response.json()


def deploy_fine_tuned_model(root: Path = REPO_ROOT, deployment_name: str = "gpt-4-1-mini-lgws-ft") -> dict[str, Any]:
    state = load_state(root)
    model_name = state.get("fine_tuned_model")
    if not model_name:
        state.setdefault("deployment_errors", []).append("No fine_tuned_model on job yet.")
        return save_state(state, root)
    if state.get("ft_deployment_name") == deployment_name and state.get("deployment_status") == "Succeeded":
        return state

    errors: list[str] = []
    for sku_name, capacity in (("DeveloperTier", 1), ("GlobalStandard", 1), ("Standard", 1)):
        try:
            data = _deploy_arm_rest(model_name, deployment_name, sku_name, capacity)
            state.update({
                "ft_deployment_name": deployment_name,
                "deployment_sku": sku_name,
                "deployment_status": data.get("properties", {}).get("provisioningState", "Submitted"),
                "deployment_result": data,
                "deployment_method": "arm-rest",
            })
            return save_state(state, root)
        except Exception as exc:
            errors.append(f"ARM/{sku_name}: {type(exc).__name__}: {str(exc)[:1500]}")

    for sku_name, capacity in (("DeveloperTier", "1"), ("GlobalStandard", "1"), ("Standard", "1")):
        args = [
            "cognitiveservices", "account", "deployment", "create",
            "--name", settings.account_name,
            "--resource-group", settings.resource_group,
            "--deployment-name", deployment_name,
            "--model-name", model_name,
            "--model-version", "1",
            "--model-format", "OpenAI",
            "--sku-name", sku_name,
            "--sku-capacity", capacity,
            "--output", "json",
        ]
        try:
            proc = _run_az(args, timeout=1200)
        except FileNotFoundError as exc:
            errors.append(f"az/{sku_name}: {type(exc).__name__}: {exc}")
            continue
        if proc.returncode == 0:
            try:
                data = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                data = {"raw": proc.stdout[-1000:]}
            state.update({
                "ft_deployment_name": deployment_name,
                "deployment_sku": sku_name,
                "deployment_status": data.get("properties", {}).get("provisioningState", "Submitted"),
                "deployment_result": data,
            })
            return save_state(state, root)
        errors.append(f"{sku_name}: {(proc.stderr or proc.stdout)[-1500:]}")
    state.update({"deployment_errors": errors})
    return save_state(state, root)


def show_delete_deployment_command(deployment_name: str = "gpt-4-1-mini-lgws-ft") -> str:
    return (
        "az cognitiveservices account deployment delete "
        f"--name {settings.account_name} --resource-group {settings.resource_group} "
        f"--deployment-name {deployment_name} --yes"
    )
