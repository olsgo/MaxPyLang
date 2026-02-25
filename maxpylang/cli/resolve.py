"""Selector and edge parsing for CLI patch operations."""

from __future__ import annotations

from .errors import ObjectResolutionError, UsageError


def resolve_selector(patch, selector: str):
    """Resolve selector to (label, object).

    Selector rules:
    - `obj-<n>` resolves by patch id.
    - `@alias:<name>` resolves by varname alias.
    - otherwise tries id first, then alias.
    """

    selector = selector.strip()
    if not selector:
        raise UsageError("selector cannot be empty")

    if selector in patch.objs:
        return selector, patch.objs[selector]

    alias = None
    if selector.startswith("@alias:"):
        alias = selector.split(":", 1)[1].strip()
        if not alias:
            raise UsageError("alias selector must be formatted as @alias:<name>")
    elif not selector.startswith("obj-"):
        alias = selector

    if alias is None:
        raise ObjectResolutionError(f"object not found: {selector}")

    matches = []
    for label, obj in patch.objs.items():
        obj_alias = obj._dict.get("box", {}).get("varname")
        if obj_alias == alias:
            matches.append((label, obj))

    if not matches:
        raise ObjectResolutionError(f"alias not found: {alias}")
    if len(matches) > 1:
        match_ids = ", ".join(label for label, _ in matches)
        raise ObjectResolutionError(
            f"alias '{alias}' is ambiguous (matches: {match_ids})"
        )

    return matches[0]


def parse_endpoint(endpoint: str):
    """Parse endpoint string `<selector>:<index>`."""

    if ":" not in endpoint:
        raise UsageError(
            f"endpoint '{endpoint}' must be formatted as <selector>:<index>"
        )

    selector, raw_index = endpoint.rsplit(":", 1)
    selector = selector.strip()
    raw_index = raw_index.strip()

    if not selector:
        raise UsageError(f"endpoint '{endpoint}' has an empty selector")

    try:
        index = int(raw_index)
    except ValueError as exc:
        raise UsageError(f"endpoint '{endpoint}' index must be an integer") from exc

    if index < 0:
        raise UsageError(f"endpoint '{endpoint}' index must be >= 0")

    return selector, index


def parse_edge(edge: str):
    """Parse edge string `<selector>:<outlet>-><selector>:<inlet>`."""

    if "->" not in edge:
        raise UsageError(
            f"edge '{edge}' must be formatted as <src>:<outlet>-><dst>:<inlet>"
        )

    src, dst = edge.split("->", 1)
    src_selector, src_index = parse_endpoint(src)
    dst_selector, dst_index = parse_endpoint(dst)
    return src_selector, src_index, dst_selector, dst_index


def resolve_outlet(patch, selector: str, index: int):
    label, obj = resolve_selector(patch, selector)
    if index >= len(obj.outs):
        raise ObjectResolutionError(
            f"outlet index {index} out of range for {label} ({len(obj.outs)} outlet(s))"
        )
    return label, obj.outs[index]


def resolve_inlet(patch, selector: str, index: int):
    label, obj = resolve_selector(patch, selector)
    if index >= len(obj.ins):
        raise ObjectResolutionError(
            f"inlet index {index} out of range for {label} ({len(obj.ins)} inlet(s))"
        )
    return label, obj.ins[index]
