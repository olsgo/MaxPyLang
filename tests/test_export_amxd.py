from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import maxpylang.cli.export_amxd as export_amxd
from maxpylang.cli.errors import UsageError, ValidationError


class _FakePatch:
    def __init__(self, patch_json: dict):
        self._patch_json = patch_json

    def get_json(self) -> dict:
        return copy.deepcopy(self._patch_json)


def test_export_amxd_file_writes_json_without_validation(tmp_path: Path) -> None:
    patch = _FakePatch({"patcher": {"boxes": [], "lines": []}})
    out_path = tmp_path / "device.amxd"

    result = export_amxd.export_amxd_file(
        patch,
        output_path=out_path,
        overwrite=False,
        validate=False,
        timeout=None,
    )

    assert result["validated"] is False
    assert out_path.exists()
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert "patcher" in payload


def test_export_amxd_file_requires_amxd_extension(tmp_path: Path) -> None:
    patch = _FakePatch({"patcher": {"boxes": [], "lines": []}})
    with pytest.raises(UsageError):
        export_amxd.export_amxd_file(
            patch,
            output_path=tmp_path / "device.maxpat",
            overwrite=False,
            validate=False,
            timeout=None,
        )


def test_export_amxd_file_refuses_overwrite_without_flag(tmp_path: Path) -> None:
    patch = _FakePatch({"patcher": {"boxes": [], "lines": []}})
    out_path = tmp_path / "device.amxd"
    out_path.write_text("{}", encoding="utf-8")

    with pytest.raises(UsageError):
        export_amxd.export_amxd_file(
            patch,
            output_path=out_path,
            overwrite=False,
            validate=False,
            timeout=None,
        )


def test_resolve_max_app_path_normalizes_binary_to_bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    app_path = tmp_path / "Max.app"
    binary_path = app_path / "Contents" / "MacOS" / "Max"
    binary_path.parent.mkdir(parents=True, exist_ok=True)
    binary_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(export_amxd, "config_get", lambda key: str(binary_path))
    monkeypatch.setattr(export_amxd, "_DEFAULT_MAX_APP_PATH", tmp_path / "Missing.app")

    resolved = export_amxd.resolve_max_app_path()
    assert resolved == app_path


def test_resolve_max_app_path_raises_when_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(export_amxd, "config_get", lambda key: str(tmp_path / "Nope.app"))
    monkeypatch.setattr(export_amxd, "_DEFAULT_MAX_APP_PATH", tmp_path / "StillNope.app")

    with pytest.raises(ValidationError):
        export_amxd.resolve_max_app_path()


def test_inject_validation_helper_remaps_object_ids(tmp_path: Path) -> None:
    patch_dict = {
        "patcher": {
            "boxes": [
                {
                    "box": {
                        "id": "obj-10",
                        "maxclass": "newobj",
                        "patching_rect": [0.0, 0.0, 60.0, 20.0],
                        "text": "cycle~ 440",
                    }
                }
            ],
            "lines": [],
        }
    }

    export_amxd._inject_validation_helper(  # noqa: SLF001 - internal helper tested directly
        patch_dict,
        validation_path=tmp_path / "validation.amxd",
    )

    boxes = patch_dict["patcher"]["boxes"]
    ids = [entry["box"]["id"] for entry in boxes]
    assert len(ids) == len(set(ids))
    assert len(boxes) >= 7
    write_boxes = [entry for entry in boxes if entry["box"].get("text", "").startswith("write ")]
    assert write_boxes
