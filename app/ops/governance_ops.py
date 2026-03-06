from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from app.ops.common import ROOT_DIR, colorize, run_cmd


@dataclass
class GovernanceCheck:
    name: str
    status: str  # pass | fail | warn
    message: str


def _status_label(status: str) -> str:
    if status == "pass":
        return colorize("PASS", "green")
    if status == "fail":
        return colorize("FAIL", "red")
    return colorize("WARN", "yellow")


def _normalize_remote_url(remote_url: str) -> str:
    return remote_url.strip().rstrip("/")


def parse_github_repo(remote_url: str) -> tuple[str, str] | None:
    value = _normalize_remote_url(remote_url)
    if not value:
        return None

    if value.startswith("git@github.com:"):
        slug = value.split(":", 1)[1]
    elif value.startswith("https://github.com/"):
        slug = value.split("https://github.com/", 1)[1]
    elif value.startswith("ssh://git@github.com/"):
        slug = value.split("ssh://git@github.com/", 1)[1]
    else:
        return None

    if slug.endswith(".git"):
        slug = slug[:-4]

    if "/" not in slug:
        return None

    owner, repo = slug.split("/", 1)
    owner = owner.strip()
    repo = repo.strip()
    if not owner or not repo:
        return None
    return owner, repo


def _extract_status_checks(payload: dict) -> set[str]:
    required_status = payload.get("required_status_checks") or {}
    contexts = required_status.get("contexts") or []
    checks = required_status.get("checks") or []

    result: set[str] = set()
    for item in contexts:
        if isinstance(item, str) and item.strip():
            result.add(item.strip())

    for item in checks:
        if isinstance(item, str) and item.strip():
            result.add(item.strip())
            continue
        if isinstance(item, dict):
            context = str(item.get("context", "")).strip()
            if context:
                result.add(context)
    return result


def _get_origin_remote_url() -> str | None:
    result = run_cmd(["git", "config", "--get", "remote.origin.url"], capture=True)
    if result.returncode != 0:
        return None
    value = (result.stdout or "").strip()
    return value or None


def _check_local_workflow() -> GovernanceCheck:
    workflow = ROOT_DIR / ".github/workflows/security-gate.yml"
    if workflow.exists() and workflow.is_file():
        return GovernanceCheck(
            name="security-gate workflow",
            status="pass",
            message="Найден .github/workflows/security-gate.yml",
        )
    return GovernanceCheck(
        name="security-gate workflow",
        status="fail",
        message="Файл .github/workflows/security-gate.yml не найден.",
    )


def _check_branch_protection(branch: str) -> GovernanceCheck:
    if shutil.which("gh") is None:
        return GovernanceCheck(
            name=f"branch protection ({branch})",
            status="warn",
            message="CLI gh не найден; удаленная проверка branch protection пропущена.",
        )

    remote_url = _get_origin_remote_url()
    if not remote_url:
        return GovernanceCheck(
            name=f"branch protection ({branch})",
            status="warn",
            message="Не удалось определить remote.origin.url.",
        )

    parsed = parse_github_repo(remote_url)
    if not parsed:
        return GovernanceCheck(
            name=f"branch protection ({branch})",
            status="warn",
            message=f"Remote не распознан как GitHub: {remote_url}",
        )

    owner, repo = parsed
    endpoint = f"repos/{owner}/{repo}/branches/{branch}/protection"
    result = run_cmd(["gh", "api", endpoint], capture=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        return GovernanceCheck(
            name=f"branch protection ({branch})",
            status="warn",
            message=f"Не удалось проверить через gh api: {err or 'unknown error'}",
        )

    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return GovernanceCheck(
            name=f"branch protection ({branch})",
            status="warn",
            message="Ответ gh api не является валидным JSON.",
        )

    has_pr_gate = payload.get("required_pull_request_reviews") is not None
    checks = _extract_status_checks(payload)
    has_security_gate = "security-gate" in checks

    if has_pr_gate and has_security_gate:
        return GovernanceCheck(
            name=f"branch protection ({branch})",
            status="pass",
            message="Включены PR gate и обязательный check security-gate.",
        )

    missing_parts: list[str] = []
    if not has_pr_gate:
        missing_parts.append("Require a pull request before merging")
    if not has_security_gate:
        missing_parts.append("status check security-gate")

    return GovernanceCheck(
        name=f"branch protection ({branch})",
        status="fail",
        message="Не хватает настроек: " + ", ".join(missing_parts),
    )


def run_governance_checks(branch: str = "main") -> tuple[list[GovernanceCheck], int]:
    checks = [
        _check_local_workflow(),
        _check_branch_protection(branch),
    ]

    has_fail = any(item.status == "fail" for item in checks)
    exit_code = 1 if has_fail else 0
    return checks, exit_code


def print_governance_checks(branch: str = "main") -> int:
    checks, exit_code = run_governance_checks(branch)
    print(f"Governance checks (branch={branch})")
    for item in checks:
        print(f"- [{_status_label(item.status)}] {item.name}: {item.message}")

    if exit_code == 0:
        print(colorize("Итог: FAIL-ошибок нет.", "green"))
    else:
        print(colorize("Итог: есть критичные проблемы (FAIL).", "red"))
    return exit_code


def print_governance_checklist() -> int:
    print("Release governance checklist:")
    print("- Branch protection для main включен.")
    print("- Require a pull request before merging включен.")
    print("- Require status checks to pass включен.")
    print("- Обязательный check security-gate добавлен.")
    print("- Последний прогон security-gate зеленый.")
    return 0

