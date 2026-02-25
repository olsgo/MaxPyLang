"""Click-based command line interface for MaxPyLang."""

from __future__ import annotations

from typing import Optional

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys

import click

from maxpylang import MaxPatch

from .errors import (
    InternalError,
    MaxPyCLIError,
    UsageError,
    ValidationError,
)
from .export_amxd import export_amxd_file
from .io import (
    collect_patch_health,
    config_get,
    config_set,
    load_patch,
    parse_attr_pairs,
    parse_point,
    parse_points,
    resolve_output_path,
    save_patch,
    serialize_object,
    strict_guard,
)
from .output import CLIContext, emit_error, emit_success
from .resolve import (
    parse_edge,
    parse_endpoint,
    resolve_inlet,
    resolve_outlet,
    resolve_selector,
)

_CONFIG_KEYS = ["max_path", "max_refpath", "packages_path", "wait_time"]
_KNOWN_COMMANDS = {
    "new",
    "list-objects",
    "place",
    "connect",
    "replace",
    "delete",
    "check",
    "save",
    "export-amxd",
    "config",
}


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--json", "json_output", is_flag=True, help="Output machine-readable JSON.")
@click.option("--verbose", is_flag=True, help="Enable verbose patch operation logs.")
@click.option("--strict", is_flag=True, help="Fail when check warnings are present.")
@click.option(
    "--in-place",
    is_flag=True,
    help="When --in is provided, write output back to the input file.",
)
@click.pass_context
def cli(ctx: click.Context, json_output: bool, verbose: bool, strict: bool, in_place: bool):
    """MaxPyLang command line interface."""

    ctx.obj = CLIContext(
        json_output=json_output,
        verbose=verbose,
        strict=strict,
        in_place=in_place,
    )


def _run_command(ctx_cfg: CLIContext, command_name: str, action):
    diagnostics: list[str] = []

    try:
        if ctx_cfg.json_output:
            captured = StringIO()
            try:
                with redirect_stdout(captured):
                    payload = action() or {}
            except Exception as exc:
                _attach_diagnostics(exc, _normalize_diagnostics(captured.getvalue()))
                raise
            diagnostics = _normalize_diagnostics(captured.getvalue())
        else:
            payload = action() or {}

        if diagnostics:
            payload.setdefault("diagnostics", [])
            payload["diagnostics"].extend(diagnostics)
            payload.setdefault("warnings", [])
            summary = f"{len(diagnostics)} internal diagnostic line(s) captured"
            if summary not in payload["warnings"]:
                payload["warnings"].append(summary)
        emit_success(ctx_cfg, command_name, payload)
    except MaxPyCLIError as exc:
        if not getattr(exc, "_cli_diagnostics", None):
            _attach_diagnostics(exc, diagnostics)
        emit_error(ctx_cfg, command_name, exc, exc.exit_code)
        raise SystemExit(exc.exit_code) from exc
    except (FileNotFoundError, IsADirectoryError) as exc:
        wrapped = UsageError(str(exc))
        _attach_diagnostics(wrapped, _extract_diagnostics(exc) or diagnostics)
        emit_error(ctx_cfg, command_name, wrapped, wrapped.exit_code)
        raise SystemExit(wrapped.exit_code) from exc
    except (AssertionError, ValueError, TypeError, KeyError) as exc:
        wrapped = ValidationError(str(exc))
        _attach_diagnostics(wrapped, _extract_diagnostics(exc) or diagnostics)
        emit_error(ctx_cfg, command_name, wrapped, wrapped.exit_code)
        raise SystemExit(wrapped.exit_code) from exc
    except click.ClickException:
        raise
    except Exception as exc:
        wrapped = InternalError(str(exc))
        _attach_diagnostics(wrapped, _extract_diagnostics(exc) or diagnostics)
        emit_error(ctx_cfg, command_name, wrapped, wrapped.exit_code)
        raise SystemExit(wrapped.exit_code) from exc


def _normalize_diagnostics(raw_output: str) -> list[str]:
    return [line.strip() for line in raw_output.splitlines() if line.strip()]


def _extract_diagnostics(exc: Exception) -> list[str]:
    diagnostics = getattr(exc, "_cli_diagnostics", [])
    if diagnostics is None:
        return []
    return list(diagnostics)


def _attach_diagnostics(exc: Exception, diagnostics: list[str]) -> None:
    if diagnostics:
        setattr(exc, "_cli_diagnostics", diagnostics)


def _context_from_args(args: list[str]) -> CLIContext:
    return CLIContext(
        json_output="--json" in args,
        verbose="--verbose" in args,
        strict="--strict" in args,
        in_place="--in-place" in args,
    )


def _infer_command_from_args(args: list[str]) -> str:
    for idx, token in enumerate(args):
        if token.startswith("-"):
            continue
        if token in _KNOWN_COMMANDS:
            if token == "config":
                for sub in args[idx + 1 :]:
                    if not sub.startswith("-"):
                        return f"config {sub}"
            return token

    for token in args:
        if not token.startswith("-"):
            return token

    return "cli"


def _json_help_response(args: list[str], ctx_cfg: CLIContext) -> int:
    captured = StringIO()
    command = _infer_command_from_args(args)
    try:
        with redirect_stdout(captured):
            cli.main(args=args, prog_name="maxpylang", standalone_mode=False)
    except SystemExit as exc:
        if isinstance(exc.code, int) and exc.code != 0:
            wrapped = UsageError("help rendering failed")
            emit_error(ctx_cfg, command, wrapped, exc.code)
            return exc.code
    except click.ClickException as exc:
        wrapped = UsageError(exc.format_message())
        emit_error(ctx_cfg, command, wrapped, exc.exit_code)
        return exc.exit_code

    help_text = captured.getvalue().rstrip()
    payload = {
        "message": f"{command} help",
        "data": {"help": help_text},
        "data_schema": f"maxpylang.cli.{command.replace(' ', '_').replace('-', '_')}.help.v1",
    }
    emit_success(ctx_cfg, command, payload)
    return 0


def _sorted_object_items(patch: MaxPatch):
    def _sort_key(item):
        label = item[0]
        if label.startswith("obj-"):
            try:
                return (0, int(label.split("-", 1)[1]))
            except ValueError:
                return (1, label)
        return (1, label)

    return sorted(patch.objs.items(), key=_sort_key)


def _finalize_mutation(
    ctx_cfg: CLIContext,
    patch: MaxPatch,
    *,
    input_path: Path,
    output_path: Path,
    message: str,
    changes: dict,
    data: Optional[dict] = None,
    data_schema: Optional[str] = None,
):
    health = collect_patch_health(patch)
    strict_guard(strict=ctx_cfg.strict, health=health)
    save_patch(patch, output_path)
    return {
        "message": message,
        "input": str(input_path),
        "output": str(output_path),
        "changes": changes,
        "warnings": health["warnings"],
        "data": data,
        "data_schema": data_schema,
    }


@cli.command("new")
@click.option("--template", type=str, help="Template path or template name.")
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output .maxpat path.",
)
@click.pass_obj
def new_command(ctx_cfg: CLIContext, template: Optional[str], output_path: Path):
    """Create a new patch from default or provided template."""

    def _action():
        patch = MaxPatch(template=template, verbose=ctx_cfg.verbose) if template else MaxPatch(verbose=ctx_cfg.verbose)
        health = collect_patch_health(patch)
        strict_guard(strict=ctx_cfg.strict, health=health)
        save_patch(patch, output_path)
        return {
            "message": "created patch",
            "output": str(output_path),
            "changes": {"objects": patch.num_objs},
            "warnings": health["warnings"],
            "data": {
                "template": template or "default",
                "objects": patch.num_objs,
            },
            "data_schema": "maxpylang.cli.new.data.v1",
        }

    _run_command(ctx_cfg, "new", _action)


@cli.command("list-objects")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.pass_obj
def list_objects_command(ctx_cfg: CLIContext, input_path: Path):
    """List objects in a patch with IDs, text, aliases, and I/O counts."""

    def _action():
        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        objects = [
            serialize_object(label, obj) for label, obj in _sorted_object_items(patch)
        ]
        return {
            "message": f"listed {len(objects)} object(s)",
            "input": str(input_path),
            "changes": {"objects": len(objects)},
            "data": {"objects": objects},
            "data_schema": "maxpylang.cli.list_objects.data.v1",
        }

    _run_command(ctx_cfg, "list-objects", _action)


@cli.command("place")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output .maxpat path.",
)
@click.option("--obj", "objects", multiple=True, required=True, help="Object text to place.")
@click.option("--randpick/--no-randpick", default=False, show_default=True)
@click.option("--num-objs", type=int, default=1, show_default=True)
@click.option("--seed", type=int)
@click.option("--weight", "weights", type=float, multiple=True, help="Weight for --randpick object selection.")
@click.option(
    "--spacing-type",
    type=click.Choice(["grid", "random", "custom", "vertical"], case_sensitive=False),
    default="grid",
    show_default=True,
)
@click.option("--spacing", type=float, multiple=True, help="Spacing values (shape depends on spacing type).")
@click.option(
    "--position",
    "positions",
    multiple=True,
    help="Custom positions formatted as x,y (repeat for each object).",
)
@click.option("--start", "start_pos", type=str, help="Starting position formatted as x,y.")
@click.pass_obj
def place_command(
    ctx_cfg: CLIContext,
    input_path: Path,
    output_path: Optional[Path],
    objects: tuple[str, ...],
    randpick: bool,
    num_objs: int,
    seed: Optional[int],
    weights: tuple[float, ...],
    spacing_type: str,
    spacing: tuple[float, ...],
    positions: tuple[str, ...],
    start_pos: Optional[str],
):
    """Place objects into an existing patch."""

    def _action():
        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        resolved_output = resolve_output_path(
            input_path=input_path,
            output_path=output_path,
            in_place=ctx_cfg.in_place,
            require_output=False,
        )

        spacing_type_norm = spacing_type.lower()
        starting_pos = parse_point(start_pos) if start_pos else None

        if not randpick and weights:
            raise UsageError("--weight can only be used with --randpick")

        weights_arg = list(weights) if weights else None

        if spacing_type_norm == "grid":
            spacing_arg = list(spacing) if spacing else [80.0, 80.0]
            if len(spacing_arg) != 2:
                raise UsageError("grid spacing requires exactly 2 values")
            if positions:
                raise UsageError("--position is only valid with --spacing-type custom")
        elif spacing_type_norm == "vertical":
            spacing_arg = list(spacing) if spacing else [80.0]
            if len(spacing_arg) != 1:
                raise UsageError("vertical spacing requires exactly 1 value")
            spacing_arg = spacing_arg[0]
            if positions:
                raise UsageError("--position is only valid with --spacing-type custom")
        elif spacing_type_norm == "random":
            if spacing:
                raise UsageError("random spacing type does not accept --spacing")
            if positions:
                raise UsageError("--position is only valid with --spacing-type custom")
            spacing_arg = [80.0, 80.0]
        else:  # custom
            if spacing:
                raise UsageError("custom spacing type does not accept --spacing")
            if not positions:
                raise UsageError("custom spacing type requires at least one --position x,y")
            spacing_arg = parse_points(positions)

        created = patch.place(
            *objects,
            randpick=randpick,
            num_objs=num_objs,
            seed=seed,
            weights=weights_arg,
            spacing_type=spacing_type_norm,
            spacing=spacing_arg,
            starting_pos=starting_pos,
            verbose=ctx_cfg.verbose,
        )
        created_ids = [obj._dict["box"]["id"] for obj in created]

        return _finalize_mutation(
            ctx_cfg,
            patch,
            input_path=input_path,
            output_path=resolved_output,
            message=f"placed {len(created_ids)} object(s)",
            changes={"placed": len(created_ids), "object_ids": created_ids},
            data={
                "placed_object_ids": created_ids,
                "spacing_type": spacing_type_norm,
                "seed": seed,
            },
            data_schema="maxpylang.cli.place.data.v1",
        )

    _run_command(ctx_cfg, "place", _action)


@cli.command("connect")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output .maxpat path.",
)
@click.option(
    "--edge",
    "edges",
    multiple=True,
    help="Edge formatted as <src>:<outlet>-><dst>:<inlet>.",
)
@click.option(
    "--from",
    "from_endpoints",
    multiple=True,
    help="Source endpoint formatted as <selector>:<outlet>.",
)
@click.option(
    "--to",
    "to_endpoints",
    multiple=True,
    help="Destination endpoint formatted as <selector>:<inlet>.",
)
@click.pass_obj
def connect_command(
    ctx_cfg: CLIContext,
    input_path: Path,
    output_path: Optional[Path],
    edges: tuple[str, ...],
    from_endpoints: tuple[str, ...],
    to_endpoints: tuple[str, ...],
):
    """Connect outlets to inlets in an existing patch."""

    def _action():
        if not edges and not from_endpoints and not to_endpoints:
            raise UsageError(
                "connect requires at least one --edge or one --from/--to pair"
            )
        if bool(from_endpoints) != bool(to_endpoints):
            raise UsageError("--from and --to must be provided together")
        if len(from_endpoints) != len(to_endpoints):
            raise UsageError("--from and --to must appear the same number of times")

        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        resolved_output = resolve_output_path(
            input_path=input_path,
            output_path=output_path,
            in_place=ctx_cfg.in_place,
            require_output=False,
        )

        connections = []
        resolved_edges = []
        for edge in edges:
            src_selector, src_index, dst_selector, dst_index = parse_edge(edge)
            src_label, outlet = resolve_outlet(patch, src_selector, src_index)
            dst_label, inlet = resolve_inlet(patch, dst_selector, dst_index)
            connections.append([outlet, inlet])
            resolved_edges.append(
                {
                    "source": {"selector": src_selector, "id": src_label, "outlet": src_index},
                    "destination": {"selector": dst_selector, "id": dst_label, "inlet": dst_index},
                    "mode": "edge",
                }
            )

        for raw_from, raw_to in zip(from_endpoints, to_endpoints):
            src_selector, src_index = parse_endpoint(raw_from)
            dst_selector, dst_index = parse_endpoint(raw_to)
            src_label, outlet = resolve_outlet(patch, src_selector, src_index)
            dst_label, inlet = resolve_inlet(patch, dst_selector, dst_index)
            connections.append([outlet, inlet])
            resolved_edges.append(
                {
                    "source": {"selector": src_selector, "id": src_label, "outlet": src_index},
                    "destination": {"selector": dst_selector, "id": dst_label, "inlet": dst_index},
                    "mode": "from_to",
                }
            )

        patch.connect(*connections, verbose=ctx_cfg.verbose)

        return _finalize_mutation(
            ctx_cfg,
            patch,
            input_path=input_path,
            output_path=resolved_output,
            message=f"connected {len(connections)} edge(s)",
            changes={"connected": len(connections)},
            data={"connections": resolved_edges},
            data_schema="maxpylang.cli.connect.data.v1",
        )

    _run_command(ctx_cfg, "connect", _action)


@cli.command("replace")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output .maxpat path.",
)
@click.option("--target", required=True, help="Target selector (obj-id or @alias:name).")
@click.option("--with", "replacement", required=True, help="Replacement object text.")
@click.option("--retain/--no-retain", default=True, show_default=True)
@click.option("--attr", "attrs", multiple=True, help="Replacement attribute as key=value.")
@click.pass_obj
def replace_command(
    ctx_cfg: CLIContext,
    input_path: Path,
    output_path: Optional[Path],
    target: str,
    replacement: str,
    retain: bool,
    attrs: tuple[str, ...],
):
    """Replace an object while preserving compatible patchcords."""

    def _action():
        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        resolved_output = resolve_output_path(
            input_path=input_path,
            output_path=output_path,
            in_place=ctx_cfg.in_place,
            require_output=False,
        )

        target_id, _ = resolve_selector(patch, target)
        parsed_attrs = parse_attr_pairs(attrs)

        patch.replace(
            target_id,
            replacement,
            retain=retain,
            verbose=ctx_cfg.verbose,
            **parsed_attrs,
        )

        new_name = patch.objs[target_id].name
        return _finalize_mutation(
            ctx_cfg,
            patch,
            input_path=input_path,
            output_path=resolved_output,
            message=f"replaced {target_id}",
            changes={"replaced": target_id, "new_name": new_name},
            data={
                "target": target_id,
                "replacement": replacement,
                "retain": retain,
                "attributes": parsed_attrs,
            },
            data_schema="maxpylang.cli.replace.data.v1",
        )

    _run_command(ctx_cfg, "replace", _action)


@cli.command("delete")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output .maxpat path.",
)
@click.option("--obj", "selectors", multiple=True, help="Object selector to delete.")
@click.option(
    "--edge",
    "edges",
    multiple=True,
    help="Edge formatted as <src>:<outlet>-><dst>:<inlet> to delete.",
)
@click.pass_obj
def delete_command(
    ctx_cfg: CLIContext,
    input_path: Path,
    output_path: Optional[Path],
    selectors: tuple[str, ...],
    edges: tuple[str, ...],
):
    """Delete objects and/or existing connections from a patch."""

    def _action():
        if not selectors and not edges:
            raise UsageError("delete requires at least one --obj or --edge")

        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        resolved_output = resolve_output_path(
            input_path=input_path,
            output_path=output_path,
            in_place=ctx_cfg.in_place,
            require_output=False,
        )

        object_ids = []
        for selector in selectors:
            label, _ = resolve_selector(patch, selector)
            object_ids.append(label)

        # Preserve order while removing duplicates.
        dedup_ids = list(dict.fromkeys(object_ids))

        cords = []
        for edge in edges:
            src_selector, src_index, dst_selector, dst_index = parse_edge(edge)
            _, outlet = resolve_outlet(patch, src_selector, src_index)
            _, inlet = resolve_inlet(patch, dst_selector, dst_index)
            cords.append([outlet, inlet])

        patch.delete(objs=dedup_ids, cords=cords, verbose=ctx_cfg.verbose)

        return _finalize_mutation(
            ctx_cfg,
            patch,
            input_path=input_path,
            output_path=resolved_output,
            message="deleted requested objects/edges",
            changes={"deleted_objects": len(dedup_ids), "deleted_edges": len(cords)},
            data={
                "deleted_object_ids": dedup_ids,
                "deleted_edges": len(cords),
            },
            data_schema="maxpylang.cli.delete.data.v1",
        )

    _run_command(ctx_cfg, "delete", _action)


@cli.command("check")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option("--unknown/--no-unknown", default=True, show_default=True)
@click.option("--js/--no-js", "js_flag", default=True, show_default=True)
@click.option("--abstractions/--no-abstractions", default=True, show_default=True)
@click.pass_obj
def check_command(
    ctx_cfg: CLIContext,
    input_path: Path,
    unknown: bool,
    js_flag: bool,
    abstractions: bool,
):
    """Inspect patch for unknown objects, js linkage, and abstractions."""

    def _action():
        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        health = collect_patch_health(patch)

        selected = {
            "unknowns": health["unknowns"] if unknown else [],
            "js": health["js"] if js_flag else {"linked": [], "unlinked": []},
            "abstractions": health["abstractions"] if abstractions else [],
        }

        warnings = []
        if unknown and selected["unknowns"]:
            warnings.append(f"{len(selected['unknowns'])} unknown object(s)")
        if js_flag and selected["js"]["unlinked"]:
            warnings.append(f"{len(selected['js']['unlinked'])} unlinked js object(s)")
        if abstractions and selected["abstractions"]:
            warnings.append(f"{len(selected['abstractions'])} abstraction object(s)")

        if ctx_cfg.strict and warnings:
            raise ValidationError(
                "strict mode failed: " + "; ".join(warnings),
                details={"warnings": warnings},
            )

        return {
            "message": "patch check completed",
            "input": str(input_path),
            "changes": {
                "unknowns": len(selected["unknowns"]),
                "js_linked": len(selected["js"]["linked"]),
                "js_unlinked": len(selected["js"]["unlinked"]),
                "abstractions": len(selected["abstractions"]),
            },
            "warnings": warnings,
            "data": selected,
            "data_schema": "maxpylang.cli.check.data.v1",
        }

    _run_command(ctx_cfg, "check", _action)


@cli.command("save")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output .maxpat path.",
)
@click.pass_obj
def save_command(ctx_cfg: CLIContext, input_path: Path, output_path: Optional[Path]):
    """Save/copy a patch file using CLI output and strict checks."""

    def _action():
        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        resolved_output = resolve_output_path(
            input_path=input_path,
            output_path=output_path,
            in_place=ctx_cfg.in_place,
            require_output=False,
        )
        health = collect_patch_health(patch)
        strict_guard(strict=ctx_cfg.strict, health=health)
        save_patch(patch, resolved_output)
        return {
            "message": "saved patch",
            "input": str(input_path),
            "output": str(resolved_output),
            "changes": {"objects": patch.num_objs},
            "warnings": health["warnings"],
            "data": {"objects": patch.num_objs},
            "data_schema": "maxpylang.cli.save.data.v1",
        }

    _run_command(ctx_cfg, "save", _action)


@cli.command("export-amxd")
@click.option(
    "--in",
    "input_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Input .maxpat path.",
)
@click.option(
    "--out",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    required=True,
    help="Output .amxd path.",
)
@click.option(
    "--validate/--no-validate",
    default=True,
    show_default=True,
    help="Open exported file in Max to validate load/save behavior.",
)
@click.option(
    "--timeout",
    type=float,
    help="Validation timeout in seconds (defaults to configured wait_time).",
)
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help="Allow replacing an existing output file.",
)
@click.pass_obj
def export_amxd_command(
    ctx_cfg: CLIContext,
    input_path: Path,
    output_path: Path,
    validate: bool,
    timeout: Optional[float],
    overwrite: bool,
):
    """Export patch JSON to `.amxd` with optional runtime validation in Max."""

    def _action():
        patch = load_patch(input_path, verbose=ctx_cfg.verbose)
        health = collect_patch_health(patch)
        strict_guard(strict=ctx_cfg.strict, health=health)

        export_data = export_amxd_file(
            patch,
            output_path=output_path,
            overwrite=overwrite,
            validate=validate,
            timeout=timeout,
        )

        message = "exported .amxd"
        if export_data["validated"]:
            message += " and validated in Max"
        elif validate:
            message += " (validation requested)"
        else:
            message += " (validation skipped)"

        return {
            "message": message,
            "input": str(input_path),
            "output": str(output_path),
            "changes": {"objects": patch.num_objs, "exported": 1},
            "warnings": health["warnings"],
            "data": export_data,
            "data_schema": "maxpylang.cli.export_amxd.data.v1",
        }

    _run_command(ctx_cfg, "export-amxd", _action)


@cli.group("config")
def config_group():
    """Read/write MaxPyLang configuration values."""


@config_group.command("get")
@click.argument("key", type=click.Choice(_CONFIG_KEYS, case_sensitive=False))
@click.pass_obj
def config_get_command(ctx_cfg: CLIContext, key: str):
    """Get a config value."""

    def _action():
        normalized = key.lower()
        value = config_get(normalized)
        return {
            "message": f"config {normalized} retrieved",
            "changes": {normalized: value},
            "data": {"key": normalized, "value": value},
            "data_schema": "maxpylang.cli.config_get.data.v1",
        }

    _run_command(ctx_cfg, "config get", _action)


@config_group.command("set")
@click.argument("key", type=click.Choice(_CONFIG_KEYS, case_sensitive=False))
@click.argument("value")
@click.pass_obj
def config_set_command(ctx_cfg: CLIContext, key: str, value: str):
    """Set a config value."""

    def _action():
        normalized = key.lower()
        updated = config_set(normalized, value)
        return {
            "message": f"config {normalized} updated",
            "changes": {normalized: updated},
            "data": {"key": normalized, "value": updated},
            "data_schema": "maxpylang.cli.config_set.data.v1",
        }

    _run_command(ctx_cfg, "config set", _action)


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    ctx_cfg = _context_from_args(args)

    if ctx_cfg.json_output and ("--help" in args or "-h" in args):
        return _json_help_response(args, ctx_cfg)

    try:
        cli.main(args=args, prog_name="maxpylang", standalone_mode=False)
        return 0
    except SystemExit as exc:
        if isinstance(exc.code, int):
            return exc.code
        return 1
    except click.ClickException as exc:
        if ctx_cfg.json_output:
            wrapped = UsageError(exc.format_message())
            emit_error(ctx_cfg, _infer_command_from_args(args), wrapped, exc.exit_code)
        else:
            exc.show()
        return exc.exit_code
    except MaxPyCLIError as exc:
        if ctx_cfg.json_output:
            emit_error(ctx_cfg, _infer_command_from_args(args), exc, exc.exit_code)
        else:
            click.echo(f"error: {exc}")
        return exc.exit_code
    except Exception as exc:
        wrapped = InternalError(str(exc))
        if ctx_cfg.json_output:
            emit_error(ctx_cfg, _infer_command_from_args(args), wrapped, wrapped.exit_code)
            return wrapped.exit_code
        raise


if __name__ == "__main__":
    raise SystemExit(main())
