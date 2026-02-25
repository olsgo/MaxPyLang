from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "maxpylang.cli.main"]


def run_cli(*args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        [*CLI, *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != expected:
        raise AssertionError(
            "CLI returned unexpected exit code\n"
            f"cmd: {' '.join([*CLI, *args])}\n"
            f"expected: {expected}\n"
            f"actual: {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\n"
            f"stderr:\n{proc.stderr}"
        )
    return proc


def run_json(*args: str, expected: int = 0) -> dict:
    proc = run_cli(*args, expected=expected)
    return json.loads(proc.stdout)


def test_connect_with_from_to_pairs(tmp_path: Path) -> None:
    patch = tmp_path / "from_to.maxpat"

    run_cli("new", "--out", str(patch))
    run_cli(
        "--in-place",
        "place",
        "--in",
        str(patch),
        "--obj",
        "cycle~ 440",
        "--obj",
        "ezdac~",
    )

    payload = run_json(
        "--json",
        "--in-place",
        "connect",
        "--in",
        str(patch),
        "--from",
        "obj-1:0",
        "--to",
        "obj-2:0",
        "--from",
        "obj-1:0",
        "--to",
        "obj-2:1",
    )

    assert payload["ok"] is True
    assert payload["schema"] == "maxpylang.cli.connect.success.v1"
    assert payload["data_schema"] == "maxpylang.cli.connect.data.v1"
    assert payload["changes"]["connected"] == 2
    assert len(payload["data"]["connections"]) == 2


def test_json_schema_metadata_for_success(tmp_path: Path) -> None:
    patch = tmp_path / "schema.maxpat"
    payload = run_json("--json", "new", "--out", str(patch))

    assert payload["ok"] is True
    assert payload["command"] == "new"
    assert payload["schema_version"] == "1.0.0"
    assert payload["schema"] == "maxpylang.cli.new.success.v1"
    assert payload["data_schema"] == "maxpylang.cli.new.data.v1"
    assert "generated_at" in payload
    assert payload["data"]["template"] == "default"


def test_json_schema_metadata_for_error(tmp_path: Path) -> None:
    patch = tmp_path / "schema_error.maxpat"
    run_cli("new", "--out", str(patch))

    payload = run_json(
        "--json",
        "connect",
        "--in",
        str(patch),
        expected=2,
    )

    assert payload["ok"] is False
    assert payload["command"] == "connect"
    assert payload["schema"] == "maxpylang.cli.connect.error.v1"
    assert payload["schema_version"] == "1.0.0"
    assert payload["data_schema"] is None
    assert payload["errors"][0]["type"] == "UsageError"
    assert payload["errors"][0]["exit_code"] == 2


def test_export_amxd_no_validate_json_schema(tmp_path: Path) -> None:
    patch = tmp_path / "export_source.maxpat"
    amxd = tmp_path / "device.amxd"

    run_cli("new", "--out", str(patch))
    payload = run_json(
        "--json",
        "export-amxd",
        "--in",
        str(patch),
        "--out",
        str(amxd),
        "--no-validate",
    )

    assert payload["ok"] is True
    assert payload["schema"] == "maxpylang.cli.export_amxd.success.v1"
    assert payload["data_schema"] == "maxpylang.cli.export_amxd.data.v1"
    assert payload["data"]["validated"] is False
    assert payload["data"]["output_extension"] == ".amxd"
    assert amxd.exists()
    exported = json.loads(amxd.read_text(encoding="utf-8"))
    assert "patcher" in exported


def test_export_amxd_requires_amxd_extension(tmp_path: Path) -> None:
    patch = tmp_path / "export_source.maxpat"
    bad_output = tmp_path / "not_amxd.maxpat"

    run_cli("new", "--out", str(patch))
    payload = run_json(
        "--json",
        "export-amxd",
        "--in",
        str(patch),
        "--out",
        str(bad_output),
        "--no-validate",
        expected=2,
    )

    assert payload["ok"] is False
    assert payload["schema"] == "maxpylang.cli.export_amxd.error.v1"
    assert payload["errors"][0]["type"] == "UsageError"
    assert ".amxd extension" in payload["message"]


def test_export_amxd_overwrite_requires_flag(tmp_path: Path) -> None:
    patch = tmp_path / "export_source.maxpat"
    amxd = tmp_path / "device.amxd"

    run_cli("new", "--out", str(patch))
    run_cli(
        "export-amxd",
        "--in",
        str(patch),
        "--out",
        str(amxd),
        "--no-validate",
    )

    payload = run_json(
        "--json",
        "export-amxd",
        "--in",
        str(patch),
        "--out",
        str(amxd),
        "--no-validate",
        expected=2,
    )
    assert payload["ok"] is False
    assert payload["errors"][0]["type"] == "UsageError"
    assert "already exists" in payload["message"]

    payload_overwrite = run_json(
        "--json",
        "export-amxd",
        "--in",
        str(patch),
        "--out",
        str(amxd),
        "--no-validate",
        "--overwrite",
    )
    assert payload_overwrite["ok"] is True


def test_export_amxd_validate_roundtrip_integration(tmp_path: Path) -> None:
    if os.environ.get("MAXPYLANG_RUN_MAX_INTEGRATION") != "1":
        pytest.skip("set MAXPYLANG_RUN_MAX_INTEGRATION=1 to run Max validation integration")
    if sys.platform != "darwin":
        pytest.skip("Max validation integration is macOS-only")
    if not Path("/Applications/Max.app").exists():
        pytest.skip("Max.app not found at /Applications/Max.app")

    patch = tmp_path / "integration_source.maxpat"
    amxd = tmp_path / "integration_device.amxd"

    run_cli("new", "--out", str(patch))
    payload = run_json(
        "--json",
        "export-amxd",
        "--in",
        str(patch),
        "--out",
        str(amxd),
        "--timeout",
        "20",
    )
    assert payload["ok"] is True
    assert payload["data"]["validated"] is True
