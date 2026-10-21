#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise navigation and the exported action without a display or haltia-kit."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from gi.repository import Gio

HERE = Path(__file__).resolve().parent.parent


def load(filename, names, namespace):
    """Load actual navigation methods, leaving GTK window construction aside."""
    tree = ast.parse((HERE / filename).read_text())
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            nodes.extend(n for n in node.body if isinstance(n, ast.FunctionDef)
                         and n.name in names)
        elif isinstance(node, ast.FunctionDef) and node.name in names:
            nodes.append(node)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
    return SimpleNamespace(**{name: namespace[name] for name in names})


MEDIA = load("media.py", ["back_action", "back_button"], {"Gio": Gio})


class BackTests(unittest.TestCase):
    def action(self, callback):
        self.app = Gio.SimpleActionGroup()
        return MEDIA.back_action(self.app, callback)

    def test_files(self):
        methods = load("haltia-files", ["listed", "up", "close_viewer", "open_file"],
                       {"os": os, "HOME": "/home/test", "Gio": Gio,
                        "media": SimpleNamespace(shown=lambda s: s)})
        obj = Mock(path="/home/test", going=1, tiles=True)
        obj.stack.get_visible_child_name.return_value = "list"
        obj.close_viewer.side_effect = lambda: methods.close_viewer(obj)
        obj.back_action = self.action(lambda: methods.up(obj))
        for path, enabled in [("/home/test", False), ("/home/test/photos", True),
                              ("/", False)]:
            methods.listed(obj, 1, path, [])
            self.assertEqual(obj.back_action.get_enabled(), enabled)
            obj.go.reset_mock()
            obj.back_action.activate(None)
            if enabled:
                obj.go.assert_called_once_with("/home/test")
            else:
                obj.go.assert_not_called()
        # A photo has a back step even when opened at either root.
        for path in ("/home/test", "/", "/home/test/photos"):
            obj.path = path
            photo = {"kind": "photo"}
            obj.shown.return_value = [photo]
            methods.open_file(obj, "/photo.jpg", photo)
            self.assertTrue(obj.back_action.get_enabled())
            obj.stack.get_visible_child_name.return_value = "viewer"
            obj.back_action.activate(None)
            obj.viewer.close.assert_called()
            self.assertEqual(obj.back_action.get_enabled(), path not in ("/home/test", "/"))

    def test_gallery(self):
        methods = load("gallery.py", ["fill", "opened", "back"],
                       {"os": os, "FILTERS": (), "Gtk": Mock(), "library": Mock(),
                        "media": SimpleNamespace(clear=lambda _w: None, shown=lambda s: s)})
        obj = Mock(kind="all", view="folders", folder=None, stale=False, scanning=False)
        obj.stack.get_visible_child_name.return_value = "browse"
        photo = {"kind": "photo", "path": "/photos/a.jpg"}
        obj.lib.items.return_value = [photo]
        obj.lib.by_folder.return_value = []
        obj.shown.return_value = [photo]
        obj.fill.side_effect = lambda **kw: methods.fill(obj, **kw)
        obj.back_action = self.action(lambda: methods.back(obj))
        methods.fill(obj)
        self.assertFalse(obj.back_action.get_enabled())
        methods.opened(obj, {"kind": "folder", "path": "/photos"})
        self.assertTrue(obj.back_action.get_enabled())
        methods.opened(obj, photo)
        obj.stack.get_visible_child_name.return_value = "viewer"
        obj.back_action.activate(None)
        self.assertTrue(obj.back_action.get_enabled())
        obj.stack.get_visible_child_name.return_value = "browse"
        obj.back_action.activate(None)
        self.assertIsNone(obj.folder)
        self.assertFalse(obj.back_action.get_enabled())
        methods.opened(obj, photo)
        obj.stack.get_visible_child_name.return_value = "viewer"
        obj.back_action.activate(None)
        self.assertFalse(obj.back_action.get_enabled())
        # A rescan that empties an opened folder also returns to the root.
        obj.folder = "/photos"
        obj.lib.items.return_value = []
        methods.fill(obj)
        self.assertIsNone(obj.folder)
        self.assertFalse(obj.back_action.get_enabled())

    def test_chooser(self):
        methods = load("chooser.py", ["_update_back", "back"], {"os": os})
        obj = Mock(path="/photos", root="/photos")
        obj.get_application.return_value.get_active_window.return_value = obj
        obj.stack.get_visible_child_name.return_value = "browse"
        obj.back_action = self.action(lambda: methods.back(obj))
        for mode in ("open", "folder", "save"):
            obj.request.mode = mode
            for path in (None, "/", "/photos", "/photos/album"):
                obj.path = path
                methods._update_back(obj)
                enabled = mode == "save" or path == "/photos/album"
                self.assertEqual(obj.back_action.get_enabled(), enabled)
                obj.go.reset_mock()
                obj.show_save.reset_mock()
                obj.back_action.activate(None)
                if path == "/photos/album":
                    obj.go.assert_called_once_with("/photos")
                elif mode == "save":
                    obj.show_save.assert_called_once()
                else:
                    obj.go.assert_not_called()
            obj.stack.get_visible_child_name.return_value = "save"
            methods._update_back(obj)
            self.assertFalse(obj.back_action.get_enabled())
            obj.stack.get_visible_child_name.return_value = "browse"
        # A background chooser cannot overwrite the focused chooser's state.
        obj.get_application.return_value.get_active_window.return_value = Mock()
        obj.back_action.set_enabled(False)
        methods._update_back(obj)
        self.assertFalse(obj.back_action.get_enabled())

    def test_portal_routes_back_to_active_window(self):
        app = Mock()
        group = Gio.SimpleActionGroup()
        app.add_action.side_effect = group.add_action
        app.lookup_action.side_effect = group.lookup_action
        callbacks = {}
        app.connect.side_effect = lambda name, cb: callbacks.update({name: cb})
        gtk = Mock()
        gtk.Application.return_value = app
        methods = load("portal.py", ["main"],
                       {"Gtk": gtk, "Gio": Gio, "Portal": Mock(), "media": MEDIA,
                        "chooser": SimpleNamespace(CHOOSER_ID="io.github.haltia_de.FileChooser"),
                        "sys": SimpleNamespace(argv=["haltia-files"])})
        methods.main()
        gtk.Application.assert_called_once_with(
            application_id="io.github.haltia_de.FileChooser")
        action = group.lookup_action("back")
        self.assertFalse(action.get_enabled())
        first, second = Mock(), Mock()
        for win in (first, second):
            app.get_active_window.return_value = win
            callbacks["notify::active-window"](app, None)
            win._update_back.assert_called_once()
            action.set_enabled(True)
            action.activate(None)
            win.back.assert_called_once()
        app.get_active_window.return_value = None
        callbacks["notify::active-window"](app, None)
        self.assertFalse(action.get_enabled())

    def test_header_corner(self):
        gtk = Mock()
        helper = load("media.py", ["back_button"], {"Gtk": gtk})
        header = Mock()
        action = self.action(lambda: None)
        button = helper.back_button(header, action)
        gtk.Box.return_value.set_size_request.assert_called_once_with(110, -1)
        gtk.Button.assert_called_once_with(label="←", action_name="app.back")
        header.pack_start.assert_called_once_with(gtk.Box.return_value)
        button.set_visible.assert_called_with(False)
        action.set_enabled(True)
        button.set_visible.assert_called_with(True)
        action.set_enabled(False)
        button.set_visible.assert_called_with(False)
        for filename in ("haltia-files", "gallery.py", "chooser.py"):
            tree = ast.parse((HERE / filename).read_text())
            # All header start children go through the reserved back corner.
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    self.assertFalse(node.func.attr == "pack_start"
                                     and ast.unparse(node.func.value) == "self.header")


if __name__ == "__main__":
    unittest.main()
