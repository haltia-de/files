#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check chooser thumbnail compatibility without GTK or haltia-kit."""
import ast
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent.parent
TREE = ast.parse((HERE / "chooser.py").read_text())
IMPORT = next(n for n in TREE.body if isinstance(n, ast.Try)
              and any(isinstance(i, ast.ImportFrom) and i.module == "haltia_kit.gallery"
                      for i in n.body))
CONSTRUCT = next(n for n in ast.walk(TREE) if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Attribute) and t.attr == "thumbs"
                         for t in n.targets))


class ThumbnailTests(unittest.TestCase):
    def test_shared_and_old_kit(self):
        for available in (True, False):
            with self.subTest(shared=available):
                kit = ModuleType("haltia_kit")
                kit.__path__ = []
                gallery = ModuleType("haltia_kit.gallery")
                shared, legacy = Mock(), Mock()
                if available:
                    gallery.Thumbs = shared
                media = ModuleType("media")
                media.Thumbs = legacy
                modules = {"haltia_kit": kit, "haltia_kit.gallery": gallery,
                           "media": media}
                window = Mock()
                namespace = {"self": window}
                with patch.dict(sys.modules, modules):
                    exec(compile(ast.Module(body=[IMPORT, CONSTRUCT], type_ignores=[]),
                                 "chooser.py", "exec"), namespace)
                selected, unused = (shared, legacy) if available else (legacy, shared)
                selected.assert_called_once_with()
                unused.assert_not_called()
                self.assertIs(window.thumbs, selected.return_value)


if __name__ == "__main__":
    unittest.main()
