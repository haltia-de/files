#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise actual file operations without GTK or haltia-kit."""
import ast
import ctypes
import errno
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent.parent
NAMES = {"rename_noreplace", "paste_file"}
tree = ast.parse((HERE / "haltia-files").read_text())
namespace = dict(ctypes=ctypes, errno=errno, os=os, shutil=shutil, tempfile=tempfile)
exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef)
                             and n.name in NAMES], type_ignores=[]),
             "haltia-files", "exec"), namespace)
rename = namespace["rename_noreplace"]
paste = namespace["paste_file"]


class OperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.src = self.root / "source"
        self.src.write_text("complete")
        self.dest = self.root / "dest"
        self.dest.mkdir()
        self.target = self.dest / "target"

    def test_rename_existing_and_dangling_symlink(self):
        for dangling in (False, True):
            if dangling:
                self.target.symlink_to("missing")
            else:
                self.target.write_text("original")
            with self.assertRaises(FileExistsError):
                rename(self.src, self.target)
            self.assertEqual(self.src.read_text(), "complete")
            if dangling:
                self.assertTrue(self.target.is_symlink())
            else:
                self.assertEqual(self.target.read_text(), "original")
            self.target.unlink()

    def test_missing_renameat2_fails_safely(self):
        with patch.object(ctypes, "CDLL", return_value=object()):
            with self.assertRaises(OSError) as error:
                rename(self.src, self.target)
        self.assertEqual(error.exception.errno, errno.ENOTSUP)
        self.assertTrue(self.src.exists())
        self.assertFalse(self.target.exists())

    def test_rename_race(self):
        # A target appearing after the preliminary check is still protected.
        self.target.write_text("original")
        with patch.object(os.path, "lexists", return_value=False):
            with self.assertRaises(FileExistsError):
                rename(self.src, self.target)
        self.assertEqual(self.target.read_text(), "original")
        self.assertTrue(self.src.exists())

    def test_rename_file_directory_and_symlink(self):
        rename(self.src, self.target)
        self.assertEqual(self.target.read_text(), "complete")
        self.src.mkdir()
        rename(self.src, self.dest / "folder")
        self.assertTrue((self.dest / "folder").is_dir())
        self.src.symlink_to("missing")
        rename(self.src, self.dest / "link")
        self.assertEqual(os.readlink(self.dest / "link"), "missing")

    def test_copy_is_hidden_until_complete(self):
        copy = shutil.copy2

        def copying(src, pending):
            self.assertFalse(self.target.exists())
            self.assertTrue(Path(pending).parent.name.startswith(".haltia-copy-"))
            return copy(src, pending)

        with patch.object(shutil, "copy2", side_effect=copying):
            paste(self.src, self.target)
        self.assertEqual(self.target.read_text(), "complete")
        self.assertEqual(list(self.dest.iterdir()), [self.target])
        self.assertTrue(self.src.exists())

    def test_failed_copy_cleans_partial_file_and_directory(self):
        for directory in (False, True):
            if directory:
                self.src.unlink()
                self.src.mkdir()
                (self.src / "child").write_text("complete")

            def failing(src, pending, **kwargs):
                if directory:
                    Path(pending).mkdir()
                    Path(pending, "child").write_text("partial")
                else:
                    Path(pending).write_text("partial")
                raise OSError("disk full")

            with patch.object(shutil, "copytree" if directory else "copy2",
                              side_effect=failing):
                with self.assertRaises(OSError):
                    paste(self.src, self.target)
            self.assertEqual(list(self.dest.iterdir()), [])
            self.assertTrue(self.src.exists())

    def test_publish_collision_cleans_temp(self):
        copy = shutil.copy2

        def copying(src, pending):
            copy(src, pending)
            self.target.write_text("new arrival")

        with patch.object(shutil, "copy2", side_effect=copying):
            with self.assertRaises(FileExistsError):
                paste(self.src, self.target)
        self.assertEqual(self.target.read_text(), "new arrival")
        self.assertEqual(list(self.dest.iterdir()), [self.target])

    def test_cut_cross_device_and_failure(self):
        def cross_device(src, target):
            if Path(src) == self.src:
                raise OSError(errno.EXDEV, "cross device")
            rename(src, target)

        with patch.dict(namespace, rename_noreplace=cross_device):
            with patch.object(shutil, "copy2", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    paste(self.src, self.target, cut=True)
            self.assertTrue(self.src.exists())
            self.assertEqual(list(self.dest.iterdir()), [])
            paste(self.src, self.target, cut=True)
        self.assertFalse(self.src.exists())
        self.assertEqual(self.target.read_text(), "complete")

    def test_copy_directory_and_cut(self):
        self.src.unlink()
        self.src.mkdir()
        (self.src / "child").write_text("complete")
        (self.src / "link").symlink_to("missing")
        paste(self.src, self.target)
        self.assertEqual((self.target / "child").read_text(), "complete")
        self.assertTrue((self.target / "link").is_symlink())
        paste(self.src, self.dest / "moved", cut=True)
        self.assertFalse(self.src.exists())


if __name__ == "__main__":
    unittest.main()
