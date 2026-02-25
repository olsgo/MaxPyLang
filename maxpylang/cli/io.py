"""I/O and normalization helpers for MaxPyLang CLI."""

from __future__ import annotations

from typing import Optional

from pathlib import Path

from maxpylang import MaxPatch
from maxpylang.tools.constants import (
    get_constant,
    set_constant,
    set_max_path,
    set_packages_path,
    set_wait_time,
)

from .errors import UsageError, ValidationError

_MAX_REFPATH_SUFFIX = "Contents/Resources/C74/docs/refpages/"


def parse_point(text: str) -> list[float]:
    """Parse a point string formatted as 'x,y'."""

    parts = [part.strip() for part in text.split(",")]
    if len(parts) != 2:
        raise UsageError(f"point '{text}' must be formatted as x,y")
    try:
        return [float(parts[0]), float(parts[1])]
    except ValueError as exc:
        raise UsageError(f"point '{text}' must contain numeric x,y values") from exc


def parse_points(values: tuple[str, ...]) -> list[list[float]]:
    return [parse_point(value) for value in values]


def parse_attr_pairs(items: tuple[str, ...]) -> dict:
    """Parse key=value items for replace/edit operations."""

    attrs = {}
    for item in items:
        if "=" not in item:
            raise UsageError(f"attribute '{item}' must be formatted as key=value")
        key, raw_value = item.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not key:
            raise UsageError(f"attribute '{item}' has an empty key")
        attrs[key] = _parse_scalar(raw_value)
    return attrs


def _parse_scalar(value: str):
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False

    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def load_patch(path: Path, *, verbose: bool = False) -> MaxPatch:
    """Load a patch from disk with consistent error semantics."""

    if not path.exists():
        raise UsageError(f"input patch not found: {path}")
    if not path.is_file():
        raise UsageError(f"input patch must be a file: {path}")

    try:
        return MaxPatch(load_file=str(path), verbose=verbose)
    except FileNotFoundError as exc:
        raise UsageError(f"input patch not found: {path}") from exc
    except Exception as exc:
        raise ValidationError(f"failed to load patch '{path}': {exc}") from exc


def resolve_output_path(
    *,
    input_path: Optional[Path],
    output_path: Optional[Path],
    in_place: bool,
    require_output: bool,
) -> Path:
    """Resolve output path policy for stateless file commands."""

    if output_path is not None:
        return output_path

    if input_path is not None and in_place:
        return input_path

    if require_output:
        if input_path is not None:
            raise UsageError("missing --out (or pass --in-place to overwrite --in)")
        raise UsageError("missing required --out")

    if input_path is not None:
        raise UsageError("missing --out (or pass --in-place to overwrite --in)")

    raise UsageError("missing output path")


def save_patch(patch: MaxPatch, output_path: Path) -> None:
    """Save patch without noisy built-in check logging."""

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        patch.save(filename=str(output_path), verbose=False, check=False)
    except Exception as exc:
        raise ValidationError(f"failed to save patch '{output_path}': {exc}") from exc


def serialize_object(label: str, obj) -> dict:
    box = obj._dict.get("box", {})
    rect = box.get("patching_rect", [None, None])
    return {
        "id": label,
        "name": obj.name,
        "text": box.get("text"),
        "alias": box.get("varname"),
        "position": [rect[0], rect[1]],
        "num_inlets": len(obj.ins),
        "num_outlets": len(obj.outs),
    }


def collect_patch_health(patch: MaxPatch) -> dict:
    """Collect check/diagnostic info without direct console printing."""

    unknowns = [serialize_object(label, obj) for label, obj in patch.get_unknowns().items()]
    js_linked, js_unlinked = patch.get_js_objs()
    abstractions = [
        serialize_object(label, obj) for label, obj in patch.get_abstractions().items()
    ]

    js_info = {
        "linked": [serialize_object(label, obj) for label, obj in js_linked.items()],
        "unlinked": [serialize_object(label, obj) for label, obj in js_unlinked.items()],
    }

    warnings = []
    if unknowns:
        warnings.append(f"{len(unknowns)} unknown object(s)")
    if js_info["unlinked"]:
        warnings.append(f"{len(js_info['unlinked'])} unlinked js object(s)")
    if abstractions:
        warnings.append(f"{len(abstractions)} abstraction object(s)")

    return {
        "unknowns": unknowns,
        "js": js_info,
        "abstractions": abstractions,
        "warnings": warnings,
    }


def strict_guard(*, strict: bool, health: dict) -> None:
    if strict and health["warnings"]:
        raise ValidationError(
            "strict mode failed: " + "; ".join(health["warnings"]),
            details={"warnings": health["warnings"]},
        )


def config_get(key: str):
    if key == "max_path":
        refpath = get_constant("max_refpath")
        suffix = _MAX_REFPATH_SUFFIX
        if refpath.endswith(suffix):
            return refpath[: -len(suffix)]
        return refpath

    if key == "max_refpath":
        return get_constant("max_refpath")

    if key == "packages_path":
        return get_constant("packages_path")

    if key == "wait_time":
        return get_constant("wait_time")

    raise UsageError(f"unsupported config key: {key}")


def config_set(key: str, value: str):
    if key == "max_path":
        set_max_path(value)
        return config_get("max_path")

    if key == "max_refpath":
        set_constant("max_refpath", value)
        return config_get("max_refpath")

    if key == "packages_path":
        set_packages_path(value)
        return config_get("packages_path")

    if key == "wait_time":
        try:
            numeric = float(value)
        except ValueError as exc:
            raise UsageError("wait_time must be numeric") from exc
        set_wait_time(numeric)
        return config_get("wait_time")

    raise UsageError(f"unsupported config key: {key}")
