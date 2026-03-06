from __future__ import annotations

from pathlib import Path

from app.ops.common import PYTHON_BIN, ROOT_DIR, print_result, run_cmd


def build_broadcast_args(
    audience: str,
    text: str | None,
    file_path: str | None,
    changelog_latest: str | None,
    limit: int | None,
    delay: float,
    dry_run: bool,
) -> list[str]:
    args = [PYTHON_BIN, "broadcast.py", "--audience", audience]

    if changelog_latest is not None:
        if changelog_latest:
            args.extend(["--changelog-latest", changelog_latest])
        else:
            args.append("--changelog-latest")
    elif file_path is not None:
        args.extend(["--file", file_path])
    elif text is not None:
        args.extend(["--text", text])
    else:
        raise ValueError("Нужно указать текст, файл или --changelog-latest.")

    if limit is not None:
        args.extend(["--limit", str(limit)])
    args.extend(["--delay", str(delay)])
    if dry_run:
        args.append("--dry-run")

    return args


def run_broadcast(
    audience: str,
    text: str | None,
    file_path: str | None,
    changelog_latest: str | None,
    limit: int | None,
    delay: float,
    dry_run: bool,
) -> int:
    args = build_broadcast_args(
        audience=audience,
        text=text,
        file_path=file_path,
        changelog_latest=changelog_latest,
        limit=limit,
        delay=delay,
        dry_run=dry_run,
    )
    result = run_cmd(args, capture=False)
    return result.returncode


def preview_broadcast(
    audience: str,
    text: str | None,
    file_path: str | None,
    changelog_latest: str | None,
    limit: int | None,
    delay: float,
) -> int:
    args = build_broadcast_args(
        audience=audience,
        text=text,
        file_path=file_path,
        changelog_latest=changelog_latest,
        limit=limit,
        delay=delay,
        dry_run=True,
    )
    result = run_cmd(args, capture=True)
    return print_result(result)


def resolve_existing_file(path_value: str) -> str:
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = ROOT_DIR / path
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Файл не найден: {path}")
    return str(path)

