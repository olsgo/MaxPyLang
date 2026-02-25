from __future__ import annotations

from typing import Optional

import unittest

from maxpylang.cli.errors import ObjectResolutionError
from maxpylang.cli.resolve import parse_edge, resolve_selector


class _FakeObject:
    def __init__(self, alias: Optional[str] = None):
        self._dict = {"box": {"varname": alias}}
        self.outs = [object()]
        self.ins = [object()]


class _FakePatch:
    def __init__(self, objs: dict):
        self.objs = objs


class ResolveTests(unittest.TestCase):
    def test_resolve_by_id(self):
        patch = _FakePatch({"obj-1": _FakeObject(alias="osc")})
        label, _ = resolve_selector(patch, "obj-1")
        self.assertEqual(label, "obj-1")

    def test_resolve_by_alias(self):
        patch = _FakePatch({"obj-1": _FakeObject(alias="osc")})
        label, _ = resolve_selector(patch, "@alias:osc")
        self.assertEqual(label, "obj-1")

    def test_ambiguous_alias_raises(self):
        patch = _FakePatch(
            {
                "obj-1": _FakeObject(alias="dup"),
                "obj-2": _FakeObject(alias="dup"),
            }
        )
        with self.assertRaises(ObjectResolutionError):
            resolve_selector(patch, "@alias:dup")

    def test_parse_edge(self):
        src_sel, src_idx, dst_sel, dst_idx = parse_edge("obj-1:0->obj-2:1")
        self.assertEqual(src_sel, "obj-1")
        self.assertEqual(src_idx, 0)
        self.assertEqual(dst_sel, "obj-2")
        self.assertEqual(dst_idx, 1)


if __name__ == "__main__":
    unittest.main()
