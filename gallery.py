# SPDX-License-Identifier: GPL-2.0
"""Галерея (b8k-files --gallery): every photo, video and sound file on the
tablet in one place, whatever folder it was saved into.

The row under the header picks Все, Фото, Видео or Музыка; the button in
the header picks how they are shown: Плитки (newest first), Список, По
датам (by month) or По папкам (a folder a row; a tap shows its files, ←
goes back). A photo opens in the viewer, a video in b8k-vplay, a sound
plays in the bar at the bottom while one goes on looking. A long press
offers Сведения and Удалить (to the trash, after a question).

What was found last time shows at once (~/.cache/b8k-files/index.json);
the home folder and the memory cards are searched again in a thread at
the start and when the window comes back after a while. The choices are
kept in ~/.config/b8k/gallery.conf.
"""
import os
import shutil
import subprocess
import threading
import time

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from b8k_compat import dialogs  # noqa: E402
from b8k_compat.settings import Settings  # noqa: E402
from gi.repository import Gdk, Gio, GLib, Gtk  # noqa: E402

import library  # noqa: E402
import media  # noqa: E402

HOME = os.path.expanduser("~")
CACHE = os.path.join(GLib.get_user_cache_dir(), "b8k-files")
SETTINGS = Settings("gallery")  # ~/.config/b8k/gallery.conf, [gallery]
# The video window (Видео's b8k-vplay), wherever it is installed; mpv else.
PLAYER = shutil.which("b8k-vplay") or shutil.which("mpv") or "/usr/local/bin/b8k-vplay"
FILTERS = (("all", "Все"), ("photo", "Фото"), ("video", "Видео"), ("audio", "Музыка"))
VIEWS = (("tiles", "Плитки"), ("list", "Список"), ("months", "По датам"),
         ("folders", "По папкам"))
RESCAN_S = 30

CSS = b"""
window, .page { background-color: #e6e6e4; }
headerbar label.title { font-size: 30px; font-weight: bold; color: #2e3436; }
headerbar label.subtitle { font-size: 18px; color: #5e5c64; }
button.place {
  background-image: none; border: none; box-shadow: none; border-radius: 16px;
  min-height: 60px; font-size: 21px; padding: 0 20px;
  background-color: #f2f2f0; color: #2e3436;
}
button.place.current { background-color: #c4dcf7; }
list, row { background-color: #f2f2f0; }
row { padding: 6px 12px; }
row:active { background-color: #c4dcf7; }
row label.name { font-size: 24px; color: #2e3436; }
row label.sub { font-size: 18px; color: #5e5c64; }
label.note { font-size: 24px; color: #5e5c64; }
"""


def load_choice(key, default, allowed):
    value = SETTINGS.get(key, default)
    return value if value in allowed else default


class Gallery(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="io.github.trudenboy.Gallery")
        self.win = None
        self.lib = library.Library(HOME, CACHE)
        self.kind = load_choice("filter", "all", dict(FILTERS))
        self.view = load_choice("view", "tiles", dict(VIEWS))
        self.folder = None  # the folder open in По папкам
        self.scanning = False
        self.scanned_at = 0.0

    # --- the window ---------------------------------------------------------
    def do_activate(self):
        if self.win:
            self.win.present()
            return
        provider = Gtk.CssProvider()
        provider.load_from_data(CSS + media.CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.win = Gtk.ApplicationWindow(application=self, title="Галерея")
        self.win.set_default_size(1160, 800)
        self.win.connect("focus-in-event", lambda *_a: self.maybe_rescan())
        self.win.connect("destroy", lambda *_a: self.bar.quit())
        self.header = Gtk.HeaderBar(title="Галерея")
        self.back_btn = Gtk.Button(label="←")
        self.back_btn.get_style_context().add_class("back")
        self.back_btn.connect("clicked", lambda *_a: self.back())
        self.back_btn.set_no_show_all(True)
        self.header.pack_start(self.back_btn)
        self.view_btn = Gtk.Button.new_from_icon_name("view-grid-symbolic",
                                                      Gtk.IconSize.DIALOG)
        self.view_btn.get_style_context().add_class("back")
        self.view_btn.connect("clicked", lambda *_a: self.pick_view())
        self.header.pack_end(self.view_btn)
        self.win.set_titlebar(self.header)

        self.thumbs = media.Thumbs(self.lib)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.stack = Gtk.Stack()
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        page.set_border_width(16)
        page.get_style_context().add_class("page")
        self.filter_box = Gtk.Box(spacing=8)
        page.pack_start(self.filter_box, False, False, 0)
        self.grid = media.Grid(self.thumbs, self.opened, self.held)
        page.pack_start(self.grid.scroll, True, True, 0)
        self.empty = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.empty.get_style_context().add_class("note")
        self.empty.set_no_show_all(True)
        page.pack_start(self.empty, True, True, 0)
        self.stack.add_named(page, "browse")
        self.viewer = media.Viewer(self.header.set_title, self.held)
        self.stack.add_named(self.viewer, "viewer")
        outer.pack_start(self.stack, True, True, 0)
        self.bar = media.SoundBar(self.thumbs, self.toast)
        outer.pack_end(self.bar, False, False, 0)
        self.win.add(outer)
        self.win.show_all()
        self.lib.load()
        self.fill()
        self.rescan()

    # --- finding the files ----------------------------------------------------
    def maybe_rescan(self):
        if time.monotonic() - self.scanned_at > RESCAN_S:
            self.rescan()
        return False

    def rescan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scanned_at = time.monotonic()
        if not self.lib.items():
            self.header.set_subtitle("ищу файлы…")

        def work():
            try:
                changed = self.lib.scan()
            except OSError:
                changed = False
            GLib.idle_add(self.scanned, changed)

        threading.Thread(target=work, daemon=True).start()

    def scanned(self, changed):
        self.scanning = False
        self.scanned_at = time.monotonic()
        if changed or not self.lib.items():
            self.fill()
        else:
            self.subtitle()
        return False

    # --- what is shown --------------------------------------------------------
    def subtitle(self):
        n = len(self.lib.items(self.kind))
        self.header.set_subtitle(library.files_word(n) if n or not self.scanning
                                 else "ищу файлы…")

    def fill(self):
        """The filter row and the files, as chosen."""
        counts = self.lib.counts()
        media.clear(self.filter_box)
        for key, label in FILTERS:
            btn = Gtk.Button(label="%s · %d" % (label, counts.get(key, 0)))
            ctx = btn.get_style_context()
            ctx.add_class("place")
            if key == self.kind:
                ctx.add_class("current")
            btn.connect("clicked", lambda _b, k=key: self.set_kind(k))
            self.filter_box.pack_start(btn, False, False, 0)
        self.filter_box.show_all()
        self.view_btn.get_image().set_from_icon_name(
            "view-list-symbolic" if self.view in ("list", "folders") else "view-grid-symbolic",
            Gtk.IconSize.DIALOG)
        self.subtitle()
        items = self.lib.items(self.kind)
        if not items:
            self.grid.show([])
            self.grid.scroll.hide()
            self.empty.set_text("Ищу фото, видео и музыку…" if self.scanning else
                                "Здесь пока ничего нет.\nСохранённые фото, видео и музыка "
                                "появятся сами.")
            self.empty.show()
            return
        self.empty.hide()
        self.grid.scroll.show()
        if self.view == "folders" and self.folder:
            inside = [i for i in items if os.path.dirname(i["path"]) == self.folder]
            if inside:
                self.header.set_title(self.lib.folder_label(self.folder))
                self.header.set_subtitle(library.files_word(len(inside)))
                self.back_btn.show()
                self.grid.show([(None, inside)])
                return
            self.folder = None
        self.header.set_title("Галерея")
        self.back_btn.hide()
        if self.view == "tiles":
            self.grid.show([(None, items)])
        elif self.view == "list":
            self.grid.show([(None, items)], rows=True)
        elif self.view == "months":
            self.grid.show(self.lib.by_month(items))
        else:
            folders = []
            for label, folder, inside in self.lib.by_folder(items):
                cover = next((i for i in inside if i["kind"] != "audio"), inside[0])
                folders.append({"kind": "folder", "label": label, "path": folder,
                                "cover": cover,
                                "sub": "%s · %s" % (library.files_word(len(inside)),
                                                    library.nice_date(inside[0]["mtime"]))})
            self.grid.show([(None, folders)], rows=True)

    def set_kind(self, kind):
        self.kind = kind
        SETTINGS.set("filter", kind)
        self.folder = None
        self.fill()

    def pick_view(self):
        if self.stack.get_visible_child_name() == "viewer":
            self.back()
        labels = [label for _k, label in VIEWS]
        current = [k for k, _l in VIEWS].index(self.view)

        choice = dialogs.choose(self.win, "Как показывать", labels, current)
        if choice is not None:
            self.set_view(VIEWS[choice][0])

    def set_view(self, view):
        self.view = view
        SETTINGS.set("view", view)
        self.folder = None
        self.fill()
        return False

    def back(self):
        if self.stack.get_visible_child_name() == "viewer":
            self.viewer.close()
            self.stack.set_visible_child_name("browse")
            self.header.set_title(self.lib.folder_label(self.folder) if self.folder
                                  else "Галерея")
            self.back_btn.set_visible(bool(self.folder))
            if self.folder:
                self.header.set_subtitle(library.files_word(len(self.shown())))
            else:
                self.subtitle()
            return
        if self.folder:
            self.folder = None
            self.fill()

    # --- opening --------------------------------------------------------------
    def shown(self):
        """The files of the page shown, in its order."""
        out = []
        for _label, items in self.grid.groups:
            out.extend(i for i in items if i.get("kind") != "folder")
        return out

    def opened(self, item):
        if item["kind"] == "folder":
            self.folder = item["path"]
            self.fill()
        elif item["kind"] == "photo":
            photos = [i for i in self.shown() if i["kind"] == "photo"]
            self.stack.set_visible_child_name("viewer")
            self.back_btn.show()
            self.header.set_subtitle("")
            self.viewer.show(photos, photos.index(item))
        elif item["kind"] == "video":
            self.bar.pause()
            if os.access(PLAYER, os.X_OK):
                subprocess.Popen(media.video_argv(PLAYER, os.path.basename(item["path"]),
                                                  item["path"]), start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            sounds = [i for i in self.shown() if i["kind"] == "audio"]
            self.bar.play(sounds, sounds.index(item))

    # --- a long press ---------------------------------------------------------
    def held(self, item):
        if item["kind"] == "folder":
            return
        name = os.path.basename(item["path"])
        actions = ["Сведения", "Удалить"]

        # After the long press has ended: a dialog inside its handler would
        # keep the gesture from seeing the finger lift.
        GLib.idle_add(self.hold_menu, name, item, actions)

    def hold_menu(self, name, item, actions):
        choice = dialogs.choose(self.win, "«%s»" % name, actions)
        if choice is None:
            return False
        if actions[choice] == "Удалить" and not dialogs.ask(
                self.win, "Удалить «%s»?" % name, "Удалить"):
            return False
        return self.act(actions[choice], item)

    def act(self, action, item):
        if action == "Сведения":
            lines = [item["path"].replace(HOME, "~", 1),
                     "%s · %s" % (library.nice_size(item["size"]),
                                  time.strftime("%d.%m.%Y %H:%M",
                                                time.localtime(item["mtime"])))]
            if item.get("duration"):
                lines.append("Длительность %s" % library.nice_duration(item["duration"]))
            if item.get("artist") or item.get("title"):
                lines.append(" — ".join(x for x in (item.get("artist"), item.get("title"))
                                        if x))
            if item["kind"] == "photo":
                try:
                    from gi.repository import GdkPixbuf

                    _f, w, h = GdkPixbuf.Pixbuf.get_file_info(item["path"])
                    if w:
                        lines.append("%d × %d точек" % (w, h))
                except Exception:
                    pass
            self.toast("\n".join(lines))
        elif action == "Удалить":
            try:
                Gio.File.new_for_path(item["path"]).trash(None)
            except GLib.Error:
                try:
                    os.unlink(item["path"])
                except OSError as exc:
                    self.toast("Не удалось удалить: %s" % exc.strerror)
                    return False
            self.lib.forget(item)
            if self.stack.get_visible_child_name() == "viewer":
                self.fill_keep()
                if not self.viewer.drop(item):
                    self.back()
            else:
                self.fill()
        return False

    def fill_keep(self):
        """The page under the viewer again, the viewer left as it is."""
        shown = self.stack.get_visible_child_name()
        self.fill()
        if shown == "viewer":
            self.back_btn.show()
            self.stack.set_visible_child_name("viewer")

    def toast(self, text):
        dialogs.info(self.win, text)
        return False
