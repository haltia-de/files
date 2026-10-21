# SPDX-License-Identifier: GPL-2.0
"""haltia-files --portal: the file chooser as an xdg-desktop-portal backend,
org.freedesktop.impl.portal.FileChooser on the bus name
org.freedesktop.impl.portal.desktop.haltia (started by D-Bus activation).

xdg-desktop-portal calls it where it is installed (haltia-portals.conf
names it for the file chooser); the Haltia shell's own small stand-in
(haltia-portal) calls it where it is not, as on the B8000-H. Programs need
nothing of their own: GTK 3 with GTK_USE_PORTAL=1 (the shell sets it),
GTK 4 and Firefox go through the portal for their file chooser.

Each OpenFile or SaveFile opens a window (chooser.Chooser) and answers
when it closes; Request.Close at the request's handle takes the window
away. The process stays IDLE seconds after the last window, so the next
chooser opens at once, then leaves the memory to the programs.
"""
import sys

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gio, GLib, Gtk  # noqa: E402

import chooser  # noqa: E402
import media  # noqa: E402

BUS_NAME = "org.freedesktop.impl.portal.desktop.haltia"
PATH = "/org/freedesktop/portal/desktop"
IDLE = 300

XML = """
<node>
  <interface name="org.freedesktop.impl.portal.FileChooser">
    <method name="OpenFile">
      <arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/>
      <arg type="a{sv}" name="results" direction="out"/>
    </method>
    <method name="SaveFile">
      <arg type="o" name="handle" direction="in"/>
      <arg type="s" name="app_id" direction="in"/>
      <arg type="s" name="parent_window" direction="in"/>
      <arg type="s" name="title" direction="in"/>
      <arg type="a{sv}" name="options" direction="in"/>
      <arg type="u" name="response" direction="out"/>
      <arg type="a{sv}" name="results" direction="out"/>
    </method>
  </interface>
  <interface name="org.freedesktop.impl.portal.Request">
    <method name="Close"/>
  </interface>
</node>
"""
NODE = Gio.DBusNodeInfo.new_for_xml(XML)
CHOOSER_IFACE = NODE.lookup_interface("org.freedesktop.impl.portal.FileChooser")
REQUEST_IFACE = NODE.lookup_interface("org.freedesktop.impl.portal.Request")


def results_variant(results):
    # Always a list, empty on Отмена: GTK 3 reads it unchecked and crashes
    # without it.
    out = {"uris": GLib.Variant("as", results.get("uris", []))}
    if results.get("current_filter"):
        out["current_filter"] = GLib.Variant("(sa(us))", results["current_filter"])
    if results.get("choices"):
        out["choices"] = GLib.Variant("a(ss)", results["choices"])
    return GLib.Variant("(ua{sv})", (results.get("response", 0), out))


class Portal:
    def __init__(self, application):
        self.application = application
        self.conn = None
        self.windows = {}  # handle -> (Chooser, request object id)
        self.idle = None

    def connected(self, conn, _name):
        """On the bus, before the name: a call that started this process by
        activation is delivered as soon as the name is ours."""
        self.conn = conn
        conn.register_object(PATH, CHOOSER_IFACE, self.method, None, None)
        self.wait()

    def method(self, conn, sender, path, iface, name, params, invocation):
        handle, app_id, _parent, title, options = params.unpack()
        mode = "save" if name == "SaveFile" else "open"
        if handle in self.windows:
            invocation.return_dbus_error("org.freedesktop.portal.Error.Failed",
                                         "a request with this handle is open")
            return
        if self.idle:
            GLib.source_remove(self.idle)
            self.idle = None
        reg = 0
        try:
            reg = conn.register_object(handle, REQUEST_IFACE,
                                       lambda *a: self.close(a[2], a[6]), None, None)
        except GLib.Error:
            pass

        answered = []

        def done(response, results):
            if answered:  # one answer per call
                return
            answered.append(response)
            entry = self.windows.pop(handle, None)
            if entry and entry[1]:
                conn.unregister_object(entry[1])
            results = dict(results, response=response)
            invocation.return_value(results_variant(results))
            self.wait()

        try:
            request = chooser.Request(mode, title, options, app_id)
            win = chooser.Chooser(request, done, self.application)
        except Exception as exc:  # a broken request must still get an answer
            if reg:
                conn.unregister_object(reg)
            sys.stderr.write("chooser: %s\n" % exc)
            if not answered:
                answered.append(2)
                invocation.return_value(GLib.Variant("(ua{sv})", (2, {})))
            self.wait()
            return
        self.windows[handle] = (win, reg)
        win.present()

    def close(self, handle, invocation):
        entry = self.windows.get(handle)
        invocation.return_value(None)
        if entry:
            entry[0].close_request()
            # The program no longer waits for this answer; xdg-desktop-portal
            # drops it, the call itself still gets one.
            entry[0].done_cb(2, {})

    def wait(self):
        if self.windows or self.idle:
            return
        self.idle = GLib.timeout_add_seconds(IDLE, self.quit)

    def quit(self):
        self.idle = None
        if not self.windows:
            self.application.quit()
        return False


def main():
    app = Gtk.Application(application_id=chooser.CHOOSER_ID)
    portal = Portal(app)

    def back():
        win = app.get_active_window()
        if win:
            win.back()

    media.back_action(app, back)

    def active_changed(_app, _prop):
        win = app.get_active_window()
        if win:
            win._update_back()
        else:
            app.lookup_action("back").set_enabled(False)

    app.connect("notify::active-window", active_changed)

    def startup(_app):
        app.hold()
        Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME, Gio.BusNameOwnerFlags.NONE,
                         portal.connected, None, lambda *_a: app.quit())

    app.connect("startup", startup)
    app.connect("activate", lambda *_a: None)
    return app.run([sys.argv[0]])
