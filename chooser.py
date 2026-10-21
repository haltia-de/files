# SPDX-License-Identifier: GPL-2.0
"""The file chooser that programs get through the portal (portal.py): one
window per request, made for one who has never seen a file system.

Open: the user's folders as large places (Недавние first: the newest files
of all of them), the files the program's filter lets through, photos and
videos as pictures, other files as rows with the date in words, newest
first. A tap picks a file; when the program takes several, a tap marks it
and the button at the bottom takes them all. Folder: places and folders
only, «Выбрать эту папку» at the bottom. Save: one screen, «Сохранить
«имя» в папку «Загрузки»», the name the program gave (or one made up) and
the folder by the kind of file; «Изменить имя» and «Другая папка» for whoever
wants them. A taken name gets « (2)»: nothing is written over. Nothing can
be deleted or renamed here; that is what Файлы is for.

The helper's switch «Все файлы при выборе» (Настройки → «Для помощника»,
~/.config/haltia/chooser.conf, all = yes) adds Дом, Система and hidden
files. The window's «✕» (the shell's) or Escape is Отмена.
"""
import os

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402

from haltia_kit import dialogs  # noqa: E402
from haltia_kit.settings import Settings  # noqa: E402

import choosing  # noqa: E402
import media  # noqa: E402

CHOOSER_ID = "io.github.haltia_de.FileChooser"
NARROW = 1000  # a screen narrower than this (portrait) gets places on top
RECENT = "Недавние"
ON_HALTIA = "Haltia" in os.environ.get("XDG_CURRENT_DESKTOP", "").split(":")

CSS = b"""
window.chooser, window.chooser .page { background-color: #e6e6e4; }
window.chooser headerbar label.title { font-size: 30px; font-weight: bold; color: #2e3436; }
window.chooser button.place, window.chooser button.filter {
  background-image: none; border: none; box-shadow: none; border-radius: 16px;
  min-height: 68px; font-size: 24px; padding: 0 20px;
  background-color: #f2f2f0; color: #2e3436;
}
window.chooser button.place label { font-size: 24px; }
window.chooser button.place.current, window.chooser button.filter.current {
  background-color: #c4dcf7;
}
window.chooser label.where { font-size: 28px; font-weight: bold; color: #2e3436; }
window.chooser label.note { font-size: 24px; color: #5e5c64; }
window.chooser list, window.chooser row { background-color: #f2f2f0; }
window.chooser row { padding: 6px 12px; }
window.chooser row:active { background-color: #c4dcf7; }
window.chooser row label.name { font-size: 24px; color: #2e3436; }
window.chooser row label.sub { font-size: 18px; color: #5e5c64; }
window.chooser label.check {
  background-color: #3584e4; color: #ffffff; font-size: 30px; font-weight: bold;
  border-radius: 24px; min-width: 48px; min-height: 48px;
}
window.chooser .bottom { background-color: #dcdcda; padding: 12px 16px; }
window.chooser button.big {
  background-image: none; border: none; box-shadow: none; border-radius: 16px;
  min-height: 76px; font-size: 26px; padding: 0 32px;
}
window.chooser button.big.accept { background-color: #3584e4; color: #ffffff; }
window.chooser button.big.accept:disabled { background-color: #99c1f1; color: #ffffff; }
window.chooser button.big.plain { background-color: #f2f2f0; color: #2e3436; }
window.chooser label.save-what { font-size: 32px; color: #2e3436; }
window.chooser label.save-where { font-size: 28px; color: #5e5c64; }
"""

_css_done = False


def _css():
    global _css_done
    if _css_done:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(media.CSS + CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    _css_done = True


def _wide():
    display = Gdk.Display.get_default()
    monitor = display.get_primary_monitor() or display.get_monitor(0) if display else None
    if monitor is None:
        return True
    return monitor.get_geometry().width >= NARROW


def _app_key(app):
    return "".join(c for c in (app or "").lower() if c.isalnum() or c in "-_") or "any"


class Request:
    """What a program asked for, from the portal's options."""

    def __init__(self, mode, title="", options=None, app=""):
        options = options or {}
        self.mode = "folder" if mode == "open" and options.get("directory") else mode
        self.app = app
        self.title = title
        self.accept = options.get("accept_label") or ""
        self.multiple = bool(options.get("multiple")) and self.mode == "open"
        self.filters = [(f[0], [tuple(r) for r in f[1]]) for f in options.get("filters") or []]
        self.filter = 0
        cur = options.get("current_filter")
        if cur:
            cur = (cur[0], [tuple(r) for r in cur[1]])
            if cur in self.filters:
                self.filter = self.filters.index(cur)
            else:
                self.filters.insert(0, cur)
        self.name = options.get("current_name") or ""
        self.folder = choosing.as_path(options.get("current_folder"))
        current_file = choosing.as_path(options.get("current_file"))
        if current_file:
            self.name = self.name or os.path.basename(current_file)
            self.folder = self.folder or os.path.dirname(current_file)
        self.choices = options.get("choices") or []

    def current_filter(self):
        return self.filters[self.filter] if self.filters else None


class Chooser(Gtk.Window):
    """done(response, results): 0 and {"uris": [...], ...}, or 1 for Отмена."""

    def __init__(self, request, done):
        super().__init__(title=request.title or self._default_title(request))
        _css()
        self.request, self.done_cb = request, done
        self.finished = False
        self.settings = Settings("chooser")
        self.everything = self.settings.get_bool("all", False)
        # A folder the program named counts only inside the places (unless
        # the helper allowed everything): one tap must not save into
        # ~/.config for a program in a sandbox.
        if request.folder and not self.everything:
            request.folder = (os.path.realpath(request.folder)
                              if choosing.allowed(request.folder) else None)
        self.marked = {}  # path -> item, for several files
        self.place = None  # the place the folder shown belongs to
        self.path = None  # the folder shown; None for Недавние
        self.root = None  # the place's own folder
        self.saving_folder = None
        self.save_name = ""
        self.get_style_context().add_class("chooser")
        self.set_default_size(1160, 800)
        if ON_HALTIA:
            self.maximize()
        self.connect("delete-event", lambda *_a: self.cancel() or True)
        self.connect("key-press-event", self._key)

        self.header = Gtk.HeaderBar(title=self.get_title())
        self.header.set_show_close_button(not ON_HALTIA)
        self.back_btn = Gtk.Button(label="←")
        self.back_btn.get_style_context().add_class("back")
        self.back_btn.connect("clicked", lambda *_a: self.back())
        self.header.pack_start(self.back_btn)
        self.set_titlebar(self.header)

        self.stack = Gtk.Stack(homogeneous=False)
        self.stack.add_named(self._browse_page(), "browse")
        if request.mode == "save":
            self.stack.add_named(self._save_page(), "save")
        self.add(self.stack)
        self.show_all()

        try:
            if request.mode == "save":
                name = request.name or choosing.new_name()
                self.saving_folder = choosing.save_folder(name, request.folder)
                self.save_name = choosing.free_name(self.saving_folder, name)
                self.show_save()
            else:
                last = self.settings.get("last." + _app_key(request.app))
                start = choosing.start_folder(request.folder, request.current_filter(), last)
                self.go(start)
        except Exception:
            # The caller answers the error; the window must not stay behind.
            self.finished = True
            self.destroy()
            raise

    @staticmethod
    def _default_title(request):
        return {"save": "Сохранение", "folder": "Выбор папки"}.get(
            request.mode, "Выбор файлов" if request.multiple else "Выбор файла")

    # --- building -----------------------------------------------------------
    def _browse_page(self):
        wide = _wide()
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL if wide
                        else Gtk.Orientation.VERTICAL, spacing=12)
        outer.get_style_context().add_class("page")
        self.places_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL if wide
                                  else Gtk.Orientation.HORIZONTAL, spacing=8)
        self.places_box.set_border_width(16)
        places = Gtk.ScrolledWindow()
        if wide:
            places.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            places.set_size_request(300, -1)
        else:
            places.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
        places.add(self.places_box)
        outer.pack_start(places, False, False, 0)

        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        inner.set_border_width(16)
        self.filters_box = Gtk.Box(spacing=8)
        self.filters_box.set_no_show_all(True)
        inner.pack_start(self.filters_box, False, False, 0)
        self.where = Gtk.Label(xalign=0)
        self.where.set_ellipsize(Pango.EllipsizeMode.START)
        self.where.get_style_context().add_class("where")
        inner.pack_start(self.where, False, False, 0)
        self.thumbs = media.Thumbs()
        # Three tiles a line: they fit beside the places in landscape and
        # across the screen in portrait.
        self.grid = media.Grid(self.thumbs, self.on_item, lambda _item: None, per_line=3)
        inner.pack_start(self.grid.scroll, True, True, 0)
        right.pack_start(inner, True, True, 0)

        self.bottom = Gtk.Box(spacing=12)
        self.bottom.get_style_context().add_class("bottom")
        self.bottom.set_no_show_all(True)
        self.accept_btn = Gtk.Button()
        for c in ("big", "accept"):
            self.accept_btn.get_style_context().add_class(c)
        self.accept_btn.connect("clicked", lambda *_a: self.accept())
        self.bottom.pack_end(self.accept_btn, False, False, 0)
        self.keep_btn = Gtk.Button(label="Не менять")
        for c in ("big", "plain"):
            self.keep_btn.get_style_context().add_class(c)
        self.keep_btn.connect("clicked", lambda *_a: self.show_save())
        self.keep_btn.set_no_show_all(True)
        self.bottom.pack_start(self.keep_btn, False, False, 0)
        right.pack_end(self.bottom, False, False, 0)
        outer.pack_start(right, True, True, 0)
        self._fill_filters()
        return outer

    def _save_page(self):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=24,
                       valign=Gtk.Align.CENTER, halign=Gtk.Align.CENTER)
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        outer.get_style_context().add_class("page")
        outer.pack_start(page, True, True, 0)
        page.set_border_width(32)
        self.save_what = Gtk.Label(wrap=True, max_width_chars=36, justify=Gtk.Justification.CENTER)
        self.save_what.get_style_context().add_class("save-what")
        page.pack_start(self.save_what, False, False, 0)
        self.save_where = Gtk.Label(wrap=True, max_width_chars=40, justify=Gtk.Justification.CENTER)
        self.save_where.get_style_context().add_class("save-where")
        page.pack_start(self.save_where, False, False, 0)
        save = Gtk.Button(label=self.request.accept or "Сохранить")
        for c in ("big", "accept"):
            save.get_style_context().add_class(c)
        save.connect("clicked", lambda *_a: self.save())
        page.pack_start(save, False, False, 12)
        row = Gtk.Box(spacing=16, halign=Gtk.Align.CENTER)
        rename = Gtk.Button(label="Изменить имя")
        rename.connect("clicked", lambda *_a: self.rename())
        other = Gtk.Button(label="Другая папка")
        other.connect("clicked", lambda *_a: self.other_folder())
        for b in (rename, other):
            for c in ("big", "plain"):
                b.get_style_context().add_class(c)
            row.pack_start(b, False, False, 0)
        page.pack_start(row, False, False, 0)
        return outer

    def _fill_filters(self):
        media.clear(self.filters_box)
        filters = self.request.filters
        if len(filters) < 2 or self.request.mode != "open":
            self.filters_box.hide()
            return
        for i, (name, _rules) in enumerate(filters):
            btn = Gtk.Button(label=name)
            btn.get_style_context().add_class("filter")
            if i == self.request.filter:
                btn.get_style_context().add_class("current")
            btn.connect("clicked", lambda _b, n=i: self.set_filter(n))
            self.filters_box.pack_start(btn, False, False, 0)
            btn.show()
        self.filters_box.show()

    def _fill_places(self):
        media.clear(self.places_box)
        items = []
        if self.request.mode == "open":
            items.append((RECENT, None))
        items += choosing.places(self.everything)
        for label, path in items:
            btn = Gtk.Button(label=label)
            btn.get_style_context().add_class("place")
            if label == self.place or (path is not None and path == self.path
                                       and self.place is None):
                btn.get_style_context().add_class("current")
            if path is None:
                btn.connect("clicked", lambda *_a: self.show_recent())
            else:
                btn.connect("clicked", lambda _b, p=path, lbl=label: self.go(p, lbl))
            self.places_box.pack_start(btn, False, False, 0)
        self.places_box.show_all()

    # --- what is shown ------------------------------------------------------
    def folders_only(self):
        return self.request.mode in ("folder", "save")

    def place_of(self, path):
        """The place a folder lies in, the deepest one."""
        best = None
        for label, root in choosing.places(self.everything):
            if path == root or path.startswith(root.rstrip("/") + "/"):
                if best is None or len(root) > len(best[1]):
                    best = (label, root)
        return best

    def go(self, path, label=None):
        entries = choosing.listing(path, self.request.current_filter(), self.folders_only(),
                                   self.everything)
        if entries is None:
            dialogs.info(self, "Эту папку нельзя открыть.")
            return
        self.path = path
        found = self.place_of(path)
        self.place = label or (found[0] if found else None)
        self.root = found[1] if found else None
        if found and path == found[1]:
            self.where.set_text(found[0])
        else:
            self.where.set_text(media.shown(os.path.basename(path.rstrip("/"))) or "Система")
        self._fill_places()
        self.show_entries(entries, "Здесь нет подходящих файлов" if not self.folders_only()
                          else "Здесь нет папок")
        self._update_back()
        self._update_bottom()

    def show_recent(self):
        roots = [p for _l, p in choosing.places(False)]
        entries = choosing.recent(roots, self.request.current_filter())
        self.path, self.place, self.root = None, RECENT, None
        self.where.set_text("Новые файлы из всех папок")
        self._fill_places()
        self.show_entries(entries, "Новых файлов нет")
        self._update_back()
        self._update_bottom()

    def show_entries(self, entries, empty):
        if not entries:
            self.grid.show([(None, [{"kind": "note", "label": empty, "sub": "",
                                     "path": None}])], rows=True)
            return
        tiles = choosing.media_share(entries) >= 0.5
        self.grid.show([(None, [self.item(e) for e in entries])], rows=not tiles)

    def item(self, entry):
        is_dir, name, path, mtime = entry
        if is_dir:
            try:
                sub = choosing.objects(len([n for n in os.listdir(path)
                                            if self.everything or not n.startswith(".")]))
            except OSError:
                sub = "нет доступа"
            return {"kind": "folder", "label": name, "path": path, "sub": sub, "dir": True}
        from haltia_kit.photos import kind_of
        item = {"path": path, "label": name, "mtime": mtime, "sub": choosing.when(mtime)}
        if self.request.multiple:
            item["marked"] = path in self.marked
        kind = kind_of(name)
        if kind:
            item["kind"] = kind
        else:
            item["kind"] = "file"
            item["gicon"] = Gio.content_type_get_icon(Gio.content_type_guess(name, None)[0])
        return item

    def _update_back(self):
        if self.stack.get_visible_child_name() == "save":
            self.back_btn.hide()
            return
        # Only when it leads somewhere: up a folder, or back to saving.
        up = self.path is not None and self.path != self.root and self.path != "/"
        self.back_btn.set_visible(up or self.request.mode == "save")

    def _update_bottom(self):
        mode = self.request.mode
        if mode == "open" and not self.request.multiple:
            self.bottom.hide()
            return
        self.keep_btn.set_visible(mode == "save")
        if mode == "open":
            n = len(self.marked)
            label = self.request.accept or "Выбрать"
            self.accept_btn.set_label("%s (%d)" % (label, n) if n else label)
            self.accept_btn.set_sensitive(n > 0)
        elif mode == "folder":
            self.accept_btn.set_label("Выбрать эту папку")
            self.accept_btn.set_sensitive(self.path is not None)
        else:
            self.accept_btn.set_label("Сохранить сюда")
            self.accept_btn.set_sensitive(self.path is not None)
        self.accept_btn.show()
        self.bottom.show()

    # --- taps ---------------------------------------------------------------
    def on_item(self, item):
        if not item.get("path"):
            return
        if item.get("dir"):
            self.go(item["path"], None)
            return
        if self.request.multiple:
            path = item["path"]
            if path in self.marked:
                del self.marked[path]
            else:
                self.marked[path] = item
            check = item.get("check")
            if check is not None:
                check.set_visible(path in self.marked)
            self._update_bottom()
            return
        self.finish([item["path"]])

    def set_filter(self, n):
        self.request.filter = n
        self._fill_filters()
        if self.path is None:
            self.show_recent()
        else:
            self.go(self.path, self.place)

    def back(self):
        if self.request.mode == "save" and (self.path is None or self.path in (self.root, "/")):
            self.show_save()
            return
        if self.path and self.path != "/":
            self.go(os.path.dirname(self.path.rstrip("/")) or "/")

    def _key(self, _w, event):
        if event.keyval == Gdk.KEY_Escape:
            self.cancel()
            return True
        return False

    def accept(self):
        mode = self.request.mode
        if mode == "open":
            self.finish(list(self.marked))
        elif mode == "folder" and self.path:
            self.finish([self.path])
        elif mode == "save" and self.path:
            self.saving_folder = self.path
            self.save_name = choosing.free_name(self.path, self.save_name)
            self.show_save()

    # --- saving -------------------------------------------------------------
    def folder_label(self, path):
        found = self.place_of(path)
        if found and path == found[1]:
            return found[0]
        return os.path.basename(path.rstrip("/")) or "Система"

    def show_save(self):
        self.save_what.set_text("Сохранить «%s»" % media.shown(self.save_name))
        self.save_where.set_text("в папку «%s»" % media.shown(
            self.folder_label(self.saving_folder)))
        self.stack.set_visible_child_name("save")
        self.header.set_title(self.get_title())
        self._update_back()

    def rename(self):
        shown = media.shown(self.save_name)
        text = dialogs.text(self, "Имя файла", shown)
        if not text or text == shown:
            return
        self.save_name = choosing.free_name(self.saving_folder, text)
        self.show_save()

    def other_folder(self):
        self.stack.set_visible_child_name("browse")
        self.go(self.saving_folder)

    def save(self):
        folder = self.saving_folder
        if not os.access(folder, os.W_OK):
            dialogs.info(self, "В эту папку нельзя сохранить. Выберите другую.")
            return
        # Taken since the screen showed it: the next free name.
        self.save_name = choosing.free_name(folder, self.save_name)
        self.finish([os.path.join(folder, self.save_name)])

    # --- the answer ---------------------------------------------------------
    def finish(self, paths):
        if self.finished or not paths:
            return
        self.finished = True
        req = self.request
        # The real place of each file: what the program gets is what was shown.
        paths = [os.path.join(os.path.realpath(os.path.dirname(p)), os.path.basename(p))
                 if req.mode == "save" else os.path.realpath(p) for p in paths]
        # Checked again as resolved now: a folder swapped for a link since
        # it was shown must not lead out of the places.
        if not self.everything and not all(
                choosing.allowed(p if req.mode == "folder" else os.path.dirname(p))
                for p in paths):
            self.finished = False
            dialogs.info(self, "Этот файл или папку выбрать нельзя.")
            return
        if req.mode != "save":
            folder = paths[0] if req.mode == "folder" else os.path.dirname(paths[0])
            self.settings.set("last." + _app_key(req.app), folder)
        results = {"uris": [Gio.File.new_for_path(p).get_uri() for p in paths]}
        if req.filters:
            results["current_filter"] = req.current_filter()
        if req.choices:
            results["choices"] = [(c[0], c[3]) for c in req.choices]
        self.done_cb(0, results)
        self.destroy()

    def cancel(self):
        if self.finished:
            return
        self.finished = True
        self.done_cb(1, {})
        self.destroy()

    def close_request(self):
        """The program took the question back (Request.Close)."""
        if not self.finished:
            self.finished = True
            self.destroy()
