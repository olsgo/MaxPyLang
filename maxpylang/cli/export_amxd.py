"""Export helpers for writing and validating Max for Live `.amxd` files."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import copy
import json
import subprocess
import sys
import time

from .errors import UsageError, ValidationError
from .io import config_get

_DEFAULT_MAX_APP_PATH = Path("/Applications/Max.app")
_IMPORT_TOOLS_PATH = Path(__file__).resolve().parents[1] / "data" / "import_tools.json"


def export_amxd_file(
    patch,
    *,
    output_path: Path,
    overwrite: bool,
    validate: bool,
    timeout: float | None,
) -> dict:
    """Write `.amxd` output and optionally validate it through Max runtime load/save."""

    normalized_output = normalize_amxd_path(output_path)

    if normalized_output.exists() and not overwrite:
        raise UsageError(
            f"output file already exists: {normalized_output} (pass --overwrite to replace)"
        )

    normalized_output.parent.mkdir(parents=True, exist_ok=True)
    _write_patch_json(patch.get_json(), normalized_output)

    resolved_timeout = (
        resolve_validation_timeout(timeout)
        if validate or timeout is not None
        else None
    )
    max_app_path = None
    validated = False

    if validate:
        max_app_path = resolve_max_app_path()
        run_max_validation(
            amxd_path=normalized_output,
            max_app_path=max_app_path,
            timeout_seconds=resolved_timeout,
        )
        validated = True

    return {
        "validated": validated,
        "validation_requested": validate,
        "max_app_path": str(max_app_path) if max_app_path else None,
        "timeout_seconds": resolved_timeout,
        "output_extension": ".amxd",
    }


def normalize_amxd_path(output_path: Path) -> Path:
    """Validate that output path is explicitly `.amxd`."""

    if output_path.suffix.lower() != ".amxd":
        raise UsageError("output path must use the .amxd extension")
    return output_path


def resolve_validation_timeout(timeout: float | None) -> float:
    """Resolve timeout from argument or CLI config."""

    raw_timeout = timeout
    if raw_timeout is None:
        raw_timeout = config_get("wait_time")

    try:
        resolved = float(raw_timeout)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"invalid validation timeout value: {raw_timeout}") from exc

    if resolved <= 0:
        raise UsageError("timeout must be greater than 0 seconds")

    return resolved


def resolve_max_app_path() -> Path:
    """Resolve configured Max app path and verify it exists."""

    configured_max_path = str(config_get("max_path")).strip()
    candidates = [Path(configured_max_path), _DEFAULT_MAX_APP_PATH]

    for candidate in candidates:
        normalized = _normalize_max_app_candidate(candidate)
        if normalized and normalized.suffix == ".app" and normalized.exists():
            return normalized

    candidate_text = ", ".join(str(_normalize_max_app_candidate(path) or path) for path in candidates)
    raise ValidationError(
        "Max.app not found. Set it with "
        "`maxpylang config set max_path /Applications/Max.app`. "
        f"Checked: {candidate_text}"
    )


def run_max_validation(
    *,
    amxd_path: Path,
    max_app_path: Path,
    timeout_seconds: float,
) -> None:
    """Validate exported `.amxd` through open and load/save roundtrip checks in Max."""

    if sys.platform != "darwin":
        raise UsageError("export-amxd validation is currently supported on macOS only")

    # First ensure Max accepts opening the target .amxd file.
    _open_in_max(max_app_path=max_app_path, file_path=amxd_path, context=".amxd")

    # Then run deterministic write+close validation using a helper-instrumented .maxpat copy.
    with TemporaryDirectory(prefix="maxpylang-amxd-validate-") as tmp_dir:
        validation_path = Path(tmp_dir) / f"{amxd_path.stem}.validation.maxpat"
        patch_dict = _load_patch_json(amxd_path)
        _write_patch_json(patch_dict, validation_path)
        _prepare_validation_file(validation_path)
        start_mtime = validation_path.stat().st_mtime

        _open_in_max(
            max_app_path=max_app_path,
            file_path=validation_path,
            context="validation .maxpat",
        )

        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            time.sleep(0.2)
            try:
                current_mtime = validation_path.stat().st_mtime
            except FileNotFoundError as exc:
                raise ValidationError("validation file disappeared during Max validation") from exc

            if current_mtime > start_mtime:
                _load_patch_json(validation_path)
                return

        raise ValidationError(
            f"timed out waiting for Max to write validation file within {timeout_seconds:.1f}s"
        )


def _open_in_max(*, max_app_path: Path, file_path: Path, context: str) -> None:
    command = ["open", "-a", str(max_app_path), str(file_path)]
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode == 0:
        return

    detail = proc.stderr.strip() or proc.stdout.strip() or "unknown open failure"
    raise ValidationError(
        f"failed to launch Max for {context}",
        details={"command": command, "stderr": detail},
    )


def _prepare_validation_file(validation_path: Path) -> None:
    patch_dict = _load_patch_json(validation_path)
    _inject_validation_helper(patch_dict, validation_path=validation_path)
    _write_patch_json(patch_dict, validation_path)


def _load_patch_json(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise
    except Exception as exc:
        raise ValidationError(f"invalid patch JSON: {path}: {exc}") from exc


def _write_patch_json(patch_dict: dict, path: Path) -> None:
    try:
        with path.open("w", encoding="utf-8") as handle:
            json.dump(patch_dict, handle, indent=2)
    except Exception as exc:
        raise ValidationError(f"failed to write patch JSON: {path}: {exc}") from exc


def _inject_validation_helper(patch_dict: dict, *, validation_path: Path) -> None:
    patcher = patch_dict.get("patcher")
    if not isinstance(patcher, dict):
        raise ValidationError("invalid patch format: missing top-level patcher dictionary")

    boxes = patcher.setdefault("boxes", [])
    lines = patcher.setdefault("lines", [])
    if not isinstance(boxes, list) or not isinstance(lines, list):
        raise ValidationError("invalid patch format: patcher boxes/lines must be arrays")

    try:
        with _IMPORT_TOOLS_PATH.open("r", encoding="utf-8") as handle:
            helper_tools = json.load(handle)
    except Exception as exc:
        raise ValidationError(f"failed to load import tools from {_IMPORT_TOOLS_PATH}: {exc}") from exc

    helper_boxes = helper_tools.get("boxes", [])
    helper_lines = helper_tools.get("lines", [])
    id_map = _build_helper_id_map(boxes=boxes, helper_boxes=helper_boxes)

    for helper_box in helper_boxes:
        cloned = copy.deepcopy(helper_box)
        box_data = cloned.get("box", {})
        original_id = box_data.get("id")
        if original_id in id_map:
            box_data["id"] = id_map[original_id]
        box_data["hidden"] = 1
        if box_data.get("text") == "write":
            escaped_path = str(validation_path).replace("\\", "\\\\").replace('"', '\\"')
            box_data["text"] = f'write "{escaped_path}"'
        boxes.append(cloned)

    for helper_line in helper_lines:
        cloned = copy.deepcopy(helper_line)
        patchline = cloned.get("patchline", {})
        source = patchline.get("source")
        destination = patchline.get("destination")

        if isinstance(source, list) and source:
            mapped_src = id_map.get(source[0])
            if mapped_src:
                source[0] = mapped_src
        if isinstance(destination, list) and destination:
            mapped_dst = id_map.get(destination[0])
            if mapped_dst:
                destination[0] = mapped_dst

        lines.append(cloned)


def _build_helper_id_map(*, boxes: list[dict], helper_boxes: list[dict]) -> dict[str, str]:
    next_index = _next_object_index(boxes) + 1
    id_map: dict[str, str] = {}

    for helper_box in helper_boxes:
        helper_id = helper_box.get("box", {}).get("id")
        if not isinstance(helper_id, str):
            raise ValidationError("invalid helper box id while constructing validation patch")
        id_map[helper_id] = f"obj-{next_index}"
        next_index += 1

    return id_map


def _next_object_index(boxes: list[dict]) -> int:
    max_id = 0
    for entry in boxes:
        box_id = entry.get("box", {}).get("id")
        if not isinstance(box_id, str):
            continue
        if not box_id.startswith("obj-"):
            continue
        try:
            index = int(box_id.split("-", 1)[1])
        except ValueError:
            continue
        max_id = max(max_id, index)
    return max_id


def _normalize_max_app_candidate(path: Path) -> Path | None:
    if not str(path):
        return None

    candidate = path.expanduser()
    if candidate.suffix == ".app":
        return candidate

    for parent in [candidate, *candidate.parents]:
        if parent.suffix == ".app":
            return parent

    return candidate
