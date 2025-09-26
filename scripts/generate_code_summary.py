"""Generate a brief purpose summary for each code file in the repository."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".css",
    ".scss",
    ".sass",
    ".html",
    ".jinja",
    ".jinja2",
    ".j2",
    ".sql",
    ".yml",
    ".yaml",
    ".ini",
}

SPECIAL_FILENAMES = {
    "Dockerfile": "Docker build instructions for the application container.",
    "Caddyfile": "Caddy reverse proxy configuration.",
}

SPECIFIC_PATHS = {
    "app/app.py": "Flask application factory and WSGI entrypoint.",
    "app/emailer.py": "Email delivery helper utilities.",
    "app/scripts/gen_sample_cert.py": "Utility script to generate sample certificates.",
    "docker-compose.yml": "Docker Compose definition for application services.",
    "alembic.ini": "Alembic migration configuration.",
    "pytest.ini": "Pytest configuration for test discovery and markers.",
}


def nice_name(value: str) -> str:
    """Turn underscores and dashes into a human-friendly phrase."""

    cleaned = value.replace("_", " ").replace("-", " ").replace(".", " ")
    cleaned = " ".join(part for part in cleaned.split() if part)
    return cleaned or value


def describe_app_file(parts: list[str], stem: str, ext: str) -> str | None:
    """Generate a description for files inside the ``app`` package."""

    if len(parts) < 2:
        return None

    section = parts[1]

    if stem == "__init__":
        return f"Package initializer for {'/'.join(parts[:-1])}."

    if section == "routes":
        return f"Flask route handlers for {nice_name(stem)}."
    if section == "models":
        return f"Database models for {nice_name(stem)}."
    if section == "services":
        return f"Business logic services for {nice_name(stem)}."
    if section == "forms":
        return f"Form definitions for {nice_name(stem)}."
    if section == "commands":
        return f"CLI command for {nice_name(stem)}."
    if section == "emails":
        return f"Email template helpers for {nice_name(stem)}."
    if section == "shared":
        if len(parts) >= 3:
            sub = parts[2]
            if sub == "templates":
                return f"Shared Jinja template for {nice_name(stem)}."
            if sub == "static":
                if len(parts) >= 4 and parts[3] == "js":
                    return f"Shared client-side script {nice_name(stem)}."
                if len(parts) >= 4 and parts[3] == "css":
                    return f"Shared stylesheet {nice_name(stem)}."
        return f"Shared utilities for {nice_name(stem)}."
    if section == "static":
        if len(parts) >= 3:
            asset_type = parts[2]
            if asset_type == "js":
                return f"Client-side script {nice_name(stem)}."
            if asset_type == "css":
                return f"Stylesheet {nice_name(stem)}."
        return f"Static asset {nice_name(stem)}."
    if section == "migrations":
        if len(parts) >= 3 and parts[2] == "versions":
            return f"Alembic migration {nice_name(stem)}."
        return "Alembic migration helper."
    if section == "templates":
        context_parts = [nice_name(part) for part in parts[2:-1]]
        context = " ".join(context_parts).strip()
        if context:
            return f"Jinja template for {context} {nice_name(stem)}."
        return f"Jinja template for {nice_name(stem)}."

    return None


def describe_path(path: str) -> str:
    parts = path.split("/")
    filename = parts[-1]
    stem, ext = os.path.splitext(filename)

    if filename in SPECIAL_FILENAMES:
        return SPECIAL_FILENAMES[filename]

    if ext and ext not in CODE_EXTENSIONS:
        return "Configuration or auxiliary file."

    if path in SPECIFIC_PATHS:
        return SPECIFIC_PATHS[path]

    if parts[0] == "app":
        description = describe_app_file(parts, stem, ext)
        if description:
            return description

    if parts[0] == "tests":
        if stem == "__init__":
            return "Package initializer for tests."
        label = nice_name(stem)
        if label.lower().startswith("test "):
            label = label[5:]
        if ext == ".py":
            return f"Pytest module covering {label}."
        return f"Test asset {label}."

    if parts[0] == "migrations":
        if len(parts) >= 2 and parts[1] == "versions":
            return f"Alembic migration {nice_name(stem)}."
        return "Alembic migration helper."

    if path == "manage.py":
        return "Flask application management script."

    if parts[0] == "caddy":
        return f"Caddy configuration {nice_name(stem)}."

    if parts[0] == "audit":
        return f"Audit tool {nice_name(stem)}."

    return f"Source file {nice_name(stem)}."


def main() -> None:
    repo_root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"]).strip().decode())
    files = subprocess.check_output(["git", "ls-files"]).decode().splitlines()

    code_files = []
    for file_path in files:
        path = Path(file_path)
        if path.name in SPECIAL_FILENAMES:
            code_files.append(path)
            continue

        if path.suffix in CODE_EXTENSIONS:
            code_files.append(path)

    output_lines = []
    for path in sorted(code_files):
        description = describe_path(path.as_posix())
        output_lines.append(f"{path.as_posix()} - {description}")

    output_file = repo_root / "code_files_summary.txt"
    output_file.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

