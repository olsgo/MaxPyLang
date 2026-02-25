from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = [sys.executable, "-m", "maxpylang.cli.main"]


class CLITestCase(unittest.TestCase):
    def run_cli(self, *args: str, expected: int = 0):
        proc = subprocess.run(
            [*CLI, *args],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != expected:
            self.fail(
                "CLI returned unexpected exit code\n"
                f"cmd: {' '.join([*CLI, *args])}\n"
                f"expected: {expected}\n"
                f"actual: {proc.returncode}\n"
                f"stdout:\n{proc.stdout}\n"
                f"stderr:\n{proc.stderr}"
            )
        return proc

    def test_end_to_end_new_place_connect_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            patch_path = Path(tmpdir) / "cli_flow.maxpat"

            self.run_cli("new", "--out", str(patch_path))
            self.run_cli(
                "--in-place",
                "place",
                "--in",
                str(patch_path),
                "--obj",
                "cycle~ 440",
                "--obj",
                "ezdac~",
                "--spacing-type",
                "grid",
                "--spacing",
                "80",
                "--spacing",
                "80",
            )
            self.run_cli(
                "--in-place",
                "connect",
                "--in",
                str(patch_path),
                "--edge",
                "obj-1:0->obj-2:0",
                "--edge",
                "obj-1:0->obj-2:1",
            )

            list_proc = self.run_cli("--json", "list-objects", "--in", str(patch_path))
            list_payload = json.loads(list_proc.stdout)
            self.assertTrue(list_payload["ok"])
            self.assertEqual(
                list_payload["schema"], "maxpylang.cli.list_objects.success.v1"
            )
            self.assertEqual(
                list_payload["data_schema"], "maxpylang.cli.list_objects.data.v1"
            )
            names = [obj["name"] for obj in list_payload["data"]["objects"]]
            self.assertIn("cycle~", names)
            self.assertIn("ezdac~", names)

            check_proc = self.run_cli("--json", "check", "--in", str(patch_path))
            check_payload = json.loads(check_proc.stdout)
            self.assertTrue(check_payload["ok"])
            self.assertEqual(check_payload["schema"], "maxpylang.cli.check.success.v1")
            self.assertEqual(
                check_payload["data_schema"], "maxpylang.cli.check.data.v1"
            )
            self.assertEqual(check_payload["changes"]["unknowns"], 0)
            self.assertTrue(patch_path.exists())

    def test_connect_invalid_selector_exit_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            patch_path = Path(tmpdir) / "bad_connect.maxpat"

            self.run_cli("new", "--out", str(patch_path))
            self.run_cli(
                "--in-place",
                "place",
                "--in",
                str(patch_path),
                "--obj",
                "cycle~ 440",
                "--obj",
                "ezdac~",
            )

            self.run_cli(
                "--in-place",
                "connect",
                "--in",
                str(patch_path),
                "--edge",
                "obj-999:0->obj-2:0",
                expected=3,
            )

    def test_config_get_set_wait_time_roundtrip(self):
        constants_path = REPO_ROOT / "maxpylang" / "data" / "constants.json"
        original_constants = constants_path.read_text(encoding="utf-8")

        try:
            get_proc = self.run_cli("--json", "config", "get", "wait_time")
            get_payload = json.loads(get_proc.stdout)
            self.assertTrue(get_payload["ok"])
            old_value = get_payload["data"]["value"]

            new_value = float(old_value) + 1.0
            set_proc = self.run_cli(
                "--json",
                "config",
                "set",
                "wait_time",
                str(new_value),
            )
            set_payload = json.loads(set_proc.stdout)
            self.assertTrue(set_payload["ok"])
            self.assertEqual(float(set_payload["data"]["value"]), new_value)
        finally:
            constants_path.write_text(original_constants, encoding="utf-8")

    def test_json_parser_error_missing_required_option(self):
        proc = self.run_cli("--json", "new", expected=2)
        payload = json.loads(proc.stdout)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "new")
        self.assertEqual(payload["schema"], "maxpylang.cli.new.error.v1")
        self.assertEqual(payload["errors"][0]["exit_code"], 2)
        self.assertIn("Missing option '--out'", payload["message"])

    def test_json_parser_error_unknown_command(self):
        proc = self.run_cli("--json", "not-a-command", expected=2)
        payload = json.loads(proc.stdout)

        self.assertFalse(payload["ok"])
        self.assertEqual(payload["command"], "not-a-command")
        self.assertEqual(payload["schema"], "maxpylang.cli.not_a_command.error.v1")
        self.assertEqual(payload["errors"][0]["exit_code"], 2)
        self.assertIn("No such command", payload["message"])

    def test_json_purity_for_internal_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            patch_path = Path(tmpdir) / "json_pure.maxpat"
            self.run_cli("new", "--out", str(patch_path))

            proc = self.run_cli(
                "--json",
                "--in-place",
                "place",
                "--in",
                str(patch_path),
                "--obj",
                "definitely_unknown_obj",
            )

            self.assertTrue(proc.stdout.lstrip().startswith("{"))
            self.assertTrue(proc.stdout.rstrip().endswith("}"))

            payload = json.loads(proc.stdout)
            self.assertTrue(payload["ok"])
            self.assertTrue(payload["diagnostics"])
            self.assertIn("internal diagnostic", " ".join(payload["warnings"]).lower())

    def test_json_help_is_wrapped(self):
        proc = self.run_cli("--json", "--help", expected=0)
        payload = json.loads(proc.stdout)

        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"], "cli")
        self.assertEqual(payload["data_schema"], "maxpylang.cli.cli.help.v1")
        self.assertIn("Usage:", payload["data"]["help"])


if __name__ == "__main__":
    unittest.main()
