#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check «Отправить» (media.sendable, media.send) without GTK or haltia-kit."""
import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent.parent
TREE = ast.parse((HERE / "media.py").read_text())
IMPORT = next(n for n in TREE.body if isinstance(n, ast.Try)
              and any(isinstance(i, ast.ImportFrom) and i.module == "haltia_kit"
                      and any(a.name == "share" for a in i.names) for i in n.body))
FUNCS = [n for n in TREE.body if isinstance(n, ast.FunctionDef)
         and n.name in ("sendable", "send")]


def load(with_share):
    kit = ModuleType("haltia_kit")
    kit.__path__ = []
    modules = {"haltia_kit": kit}
    if with_share:
        kit.share = ModuleType("haltia_kit.share")
        kit.share.send = Mock()
        modules["haltia_kit.share"] = kit.share
    else:
        modules["haltia_kit.share"] = None  # import fails, as with an older kit
    namespace = {}
    with patch.dict(sys.modules, modules):
        exec(compile(ast.Module(body=[IMPORT] + FUNCS, type_ignores=[]),
                     "media.py", "exec"), namespace)
    return namespace


class ShareTests(unittest.TestCase):
    def test_files_with_share(self):
        ns = load(True)
        self.assertTrue(ns["sendable"]({"path": "/a.jpg", "kind": "photo"}))
        self.assertTrue(ns["sendable"]({"path": "/a.txt", "kind": "file"}))
        self.assertFalse(ns["sendable"]({"path": "/d", "kind": "folder", "dir": True}))
        self.assertFalse(ns["sendable"]({"path": None, "kind": "note"}))
        win = object()
        ns["send"](win, "/a.jpg")
        ns["share"].send.assert_called_once_with("/a.jpg", win)

    def test_hidden_without_share(self):
        ns = load(False)
        self.assertIsNone(ns["share"])
        self.assertFalse(ns["sendable"]({"path": "/a.jpg", "kind": "photo"}))


if __name__ == "__main__":
    unittest.main()
