#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exercise navigation and the exported action without a display or haltia-kit."""
import ast
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from gi.repository import Gio

HERE = Path(__file__).resolve().parent.parent

# Run inside dbus-run-session: start the portal (argv[1] is haltia-files)
# and ask the bus what the shell and xdg-desktop-portal will ask.
BUS_CHECK = r'''
import subprocess, sys, time
from gi.repository import Gio, GLib

PORTAL = "org.freedesktop.impl.portal.desktop.haltia"
CHOOSER = "io.github.haltia_de.FileChooser"
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)


def call(name, path, iface, method, args, reply):
    return bus.call_sync(name, path, iface, method, args, GLib.VariantType(reply),
                         Gio.DBusCallFlags.NONE, 5000, None).unpack()[0]


def owned(name):
    return call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                "NameHasOwner", GLib.Variant("(s)", (name,)), "(b)")


proc = subprocess.Popen([sys.executable, sys.argv[1], "--portal"])
try:
    start = time.monotonic()
    while not (owned(PORTAL) and owned(CHOOSER)):
        if proc.poll() is not None:
            sys.exit("the portal exited with %s" % proc.returncode)
        if time.monotonic() - start > 5:
            sys.exit("names not owned after 5 s: %s %s" % (owned(PORTAL), owned(CHOOSER)))
        time.sleep(0.05)
    xml = call(PORTAL, "/org/freedesktop/portal/desktop",
               "org.freedesktop.DBus.Introspectable", "Introspect", None, "(s)")
    if "org.freedesktop.impl.portal.FileChooser" not in xml:
        sys.exit("no FileChooser interface:\n" + xml)
    enabled, _param, _state = call(CHOOSER, "/io/github/haltia_de/FileChooser",
                                   "org.gtk.Actions", "Describe",
                                   GLib.Variant("(s)", ("back",)), "((bgav))")
    if enabled:
        sys.exit("app.back is enabled with no chooser open")
finally:
    proc.terminate()
    proc.wait(10)
'''


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
        gtk = Mock()
        methods = load("chooser.py", ["_update_back", "back"], {"os": os, "Gtk": gtk})
        obj = Mock(path="/photos", root="/photos")
        gtk.Window.list_toplevels.return_value = [obj]
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
        gtk.Window.list_toplevels.return_value = [obj, Mock(**{"is_active.return_value": True})]
        obj.back_action.set_enabled(False)
        methods._update_back(obj)
        self.assertFalse(obj.back_action.get_enabled())

    def test_portal(self):
        gio = SimpleNamespace(SimpleActionGroup=Gio.SimpleActionGroup,
                              BusNameOwnerFlags=Gio.BusNameOwnerFlags,
                              bus_own_name_on_connection=Mock())
        iface = object()
        methods = load("portal.py", ["__init__", "connected", "back"],
                       {"Gio": gio, "media": MEDIA, "chooser": SimpleNamespace(
                           CHOOSER_ID="io.github.haltia_de.FileChooser"),
                        "PATH": "/org/freedesktop/portal/desktop", "CHOOSER_IFACE": iface})
        portal = SimpleNamespace(wait=Mock(), method=Mock())
        portal.back = lambda: methods.back(portal)
        methods.__init__(portal)
        conn = Mock()
        methods.connected(portal, conn, "portal")
        conn.export_action_group.assert_called_once_with(
            "/io/github/haltia_de/FileChooser", portal.actions)
        gio.bus_own_name_on_connection.assert_called_once_with(
            conn, "io.github.haltia_de.FileChooser", Gio.BusNameOwnerFlags.NONE, None, None)
        conn.register_object.assert_called_once_with(
            "/org/freedesktop/portal/desktop", iface, portal.method, None, None)
        action = portal.actions.lookup_action("back")
        self.assertFalse(action.get_enabled())
        action.set_enabled(True)
        action.activate(None)  # no window: nothing to do
        # «Back» goes to the chooser in front, else to the newest one.
        first = Mock(**{"is_active.return_value": False})
        second = Mock(**{"is_active.return_value": False})
        portal.windows = {"/a": (first, 0), "/b": (second, 0)}
        first.is_active.return_value = True
        action.activate(None)
        first.back.assert_called_once()
        second.back.assert_not_called()
        first.is_active.return_value = False
        action.activate(None)
        second.back.assert_called_once()
        self.assertEqual(first.back.call_count, 1)

    @unittest.skipUnless(shutil.which("dbus-run-session")
                         and importlib.util.find_spec("haltia_kit"),
                         "needs dbus-run-session and haltia-kit")
    def test_portal_on_bus(self):
        """`haltia-files --portal` on a fresh session bus: both names soon,
        the FileChooser interface, and app.back for the shell."""
        with tempfile.TemporaryDirectory() as home:
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("DBUS_", "GTK_"))}
            env.update(HOME=home, XDG_CONFIG_HOME=os.path.join(home, ".config"),
                       XDG_CACHE_HOME=os.path.join(home, ".cache"),
                       XDG_DATA_HOME=os.path.join(home, ".local/share"))
            run = subprocess.run(
                ["dbus-run-session", "--", sys.executable, "-c", BUS_CHECK,
                 str(HERE / "haltia-files")],
                env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

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
