"""Output helpers for consistent human and JSON CLI responses."""

from __future__ import annotations

from typing import Optional

from dataclasses import dataclass
from datetime import datetime, timezone
import json

import click

SCHEMA_VERSION = "1.0.0"


@dataclass
class CLIContext:
    json_output: bool
    verbose: bool
    strict: bool
    in_place: bool


def _schema_key(command: str, kind: str) -> str:
    normalized = command.strip().replace(" ", "_").replace("-", "_")
    return f"maxpylang.cli.{normalized}.{kind}.v1"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def emit_success(ctx: CLIContext, command: str, payload: Optional[dict] = None) -> None:
    payload = payload or {}
    output = {
        "ok": True,
        "command": command,
        "schema_version": SCHEMA_VERSION,
        "schema": payload.get("schema", _schema_key(command, "success")),
        "data_schema": payload.get("data_schema", _schema_key(command, "data")),
        "generated_at": _timestamp(),
        "message": payload.get("message", f"{command} completed"),
        "input": payload.get("input"),
        "output": payload.get("output"),
        "changes": payload.get("changes", {}),
        "warnings": payload.get("warnings", []),
        "data": payload.get("data"),
        "diagnostics": payload.get("diagnostics", []),
        "errors": [],
    }

    if ctx.json_output:
        click.echo(json.dumps(output, indent=2))
        return

    click.echo(output["message"])
    if output["input"]:
        click.echo(f"input: {output['input']}")
    if output["output"]:
        click.echo(f"output: {output['output']}")

    changes = output["changes"]
    if changes:
        if isinstance(changes, dict):
            for key in sorted(changes.keys()):
                click.echo(f"{key}: {changes[key]}")
        else:
            click.echo(f"changes: {changes}")

    for warning in output["warnings"]:
        click.echo(f"warning: {warning}")


def emit_error(ctx: CLIContext, command: str, error: Exception, exit_code: int) -> None:
    message = str(error)
    error_type = type(error).__name__
    diagnostics = getattr(error, "_cli_diagnostics", [])
    output = {
        "ok": False,
        "command": command,
        "schema_version": SCHEMA_VERSION,
        "schema": _schema_key(command, "error"),
        "data_schema": None,
        "generated_at": _timestamp(),
        "message": message,
        "input": None,
        "output": None,
        "changes": {},
        "warnings": [],
        "data": None,
        "diagnostics": diagnostics,
        "errors": [{"type": error_type, "message": message, "exit_code": exit_code}],
    }

    if ctx.json_output:
        click.echo(json.dumps(output, indent=2))
        return

    click.echo(f"error: {message}")
