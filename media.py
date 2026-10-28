# SPDX-License-Identifier: GPL-2.0
"""What Файлы and Галерея share for media on top of haltia-kit: tiles and
rows with small pictures, a grid that is built as one scrolls (Grid), the
photo viewer for items (Viewer) and the sound bar at the bottom (SoundBar).
Small pictures, the viewer itself and sound are haltia_kit's (photos.Thumbs,
photos.Viewer, sound.Player).
"""
import os

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from haltia_kit import photos, sound  # noqa: E402
from gi.repository import Gio, GLib, Gtk, Pango  # noqa: E402

try:
    from haltia_kit import share  # noqa: E402
except ImportError:  # an older kit: no «Отправить»
    share = None

import library  # noqa: E402


def sendable(item):
    """Whether «Отправить» is offered for an item: a file, and a kit that
    has haltia_kit.share."""
    return (share is not None and bool(item.get("path")) and not item.get("dir")
            and item.get("kind") not in ("folder", "note"))


def send(win, path):
    """Offers a file to the programs that take it (haltia_kit.share)."""
    share.send(path, win)


def back_action(app, callback):
    """The shell and the header use the same exported action."""
    action = Gio.SimpleAction.new("back", None)
    action.set_enabled(False)
    action.connect("activate", lambda *_a: callback())
    app.add_action(action)
    return action


def back_button(header, action):
    # Keep the shell's home button and the title out of each other's way.
    corner = Gtk.Box()
    corner.set_size_request(110, -1)
    button = Gtk.Button(label="←", action_name="app.back")
    button.get_style_context().add_class("back")
    button.set_no_show_all(True)
    changed = action.connect("notify::enabled",
                             lambda *_a: button.set_visible(action.get_enabled()))
    button.connect("destroy", lambda *_a: action.disconnect(changed))
    button.set_visible(action.get_enabled())
    corner.pack_start(button, False, False, 0)
    header.pack_start(corner)
    return button


TILE = 208  # px of a tile's picture; five fit beside the panel
ROW_PIC = 88
CHUNK = 60  # tiles added at a time, more as one scrolls near the end
# Tiles built before a new folder's first frame; the rest of its first CHUNK
# follows in low-priority idle steps of this size, after the frame is drawn.
FIRST = 20
SHOWN_MAX = 600  # tiles built until «Показать ещё»: each keeps its small picture
ICONS = {"photo": "image-x-generic", "video": "video-x-generic", "audio": "audio-x-generic",
         "folder": "folder"}

CSS = b"""
.tile { background-color: #f2f2f0; border-radius: 12px; }
.tile label.cap { font-size: 18px; color: #2e3436; }
.tile label.badge { background-color: rgba(0,0,0,0.6); color: #ffffff; font-size: 17px;
  border-radius: 8px; padding: 2px 8px; }
flowboxchild { padding: 0; border-radius: 12px; }
flowboxchild:active { background-color: #c4dcf7; }
button.more { background-image: none; border: none; box-shadow: none; border-radius: 16px;
  min-height: 60px; font-size: 21px; margin: 8px 0; background-color: #f2f2f0; color: #2e3436; }
label.section { font-size: 26px; font-weight: bold; color: #2e3436; margin: 12px 4px 4px 4px; }
.soundbar { background-color: #dcdcda; padding: 8px 16px; }
.soundbar label.ttl { font-size: 22px; font-weight: bold; color: #2e3436; }
.soundbar label.sub { font-size: 18px; color: #5e5c64; }
.soundbar button { background-image: none; background-color: #f2f2f0; color: #2e3436;
  border: 1px solid #c0bfbc; box-shadow: none; border-radius: 14px;
  min-height: 64px; min-width: 72px; font-size: 26px; }
.soundbar scale { min-height: 40px; }
button.send { background-image: none; border: none; box-shadow: none; border-radius: 16px;
  min-height: 72px; font-size: 26px; padding: 0 28px; margin: 16px;
  background-color: #3584e4; color: #ffffff; }
"""


def video_argv(player, title, path):
    """The command that plays a video: haltia-vplay, or mpv on a desktop
    without it (mpv takes its options as --name=value)."""
    if os.path.basename(player) == "mpv":
        return [player, "--fs", "--title=" + title, "--", path]
    return [player, "--title", title, path]


def clear(box):
    for child in box.get_children():
        box.remove(child)
        child.destroy()


def Thumbs(_lib=None):
    """Small pictures (haltia_kit.photos.Thumbs): want(path, image, size)."""
    return photos.Thumbs()


def icon_image(item, size):
    """A stand-in picture by kind (or an item's own "gicon") until its small
    picture comes."""
    if isinstance(item, dict) and item.get("gicon") is not None:
        image = Gtk.Image.new_from_gicon(item["gicon"], Gtk.IconSize.DIALOG)
    else:
        kind = item["kind"] if isinstance(item, dict) else item
        image = Gtk.Image.new_from_icon_name(ICONS.get(kind, "text-x-generic"),
                                             Gtk.IconSize.DIALOG)
    image.set_pixel_size(size // 2)
    image.set_size_request(size, size)
    return image


def shown(name):
    """A file name as text GTK takes: bytes that are not UTF-8 become �."""
    return GLib.filename_display_name(name)


def caption(item):
    if item["kind"] == "audio" and item.get("title"):
        return item["title"]
    return shown(os.path.basename(item["path"]))


def subline(item):
    if "sub" in item:
        return item["sub"]
    parts = [library.nice_date(item["mtime"])]
    if item.get("artist"):
        parts.insert(0, item["artist"])
    if item.get("duration"):
        parts.append(library.nice_duration(item["duration"]))
    parts.append(library.nice_size(item["size"]))
    return " · ".join(parts)


def tile(item, thumbs, size=TILE):
    """A square picture; video with its length on it, video and sound with
    a caption under it. item may be a folder: {"kind": "folder", ...}."""
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.get_style_context().add_class("tile")
    over = Gtk.Overlay()
    image = icon_image(item, size)
    over.add(image)
    if item["kind"] == "video" and item.get("duration"):
        badge = Gtk.Label(label="▶ " + library.nice_duration(item["duration"]),
                          halign=Gtk.Align.END, valign=Gtk.Align.END, margin=8)
        badge.get_style_context().add_class("badge")
        over.add_overlay(badge)
    if "marked" in item:
        over.add_overlay(check(item, Gtk.Align.END, Gtk.Align.START))
    box.pack_start(over, False, False, 0)
    if item["kind"] != "photo" or item.get("label"):
        cap = Gtk.Label(label=shown(item.get("label") or caption(item)), max_width_chars=1)
        cap.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        cap.set_size_request(size, -1)
        cap.get_style_context().add_class("cap")
        box.pack_start(cap, False, False, 4)
    want(thumbs, item, image, size)
    return box


def want(thumbs, item, image, size):
    if item["kind"] in library.KINDS:
        thumbs.want(item["path"], image, size)
    elif item.get("cover"):
        thumbs.want(item["cover"]["path"], image, size)


def row_box(item, thumbs, sub=None):
    box = Gtk.Box(spacing=16)
    image = icon_image(item, ROW_PIC)
    want(thumbs, item, image, ROW_PIC)
    box.pack_start(image, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    name = Gtk.Label(label=shown(item.get("label") or caption(item)), xalign=0)
    name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    name.get_style_context().add_class("name")
    text.pack_start(name, False, False, 0)
    small = Gtk.Label(label=sub if sub is not None else subline(item), xalign=0)
    small.set_ellipsize(Pango.EllipsizeMode.END)
    small.get_style_context().add_class("sub")
    if "sub_label" in item:  # a line that comes later (a folder's count)
        item["sub_label"] = small
    text.pack_start(small, False, False, 0)
    box.pack_start(text, True, True, 0)
    if "marked" in item:
        box.pack_end(check(item, Gtk.Align.CENTER, Gtk.Align.CENTER), False, False, 0)
    return box


def check(item, halign, valign):
    """The mark of a file chosen among several (the file chooser's): shown
    while item["marked"], kept as item["check"] to show or hide later."""
    mark = Gtk.Label(label="✓", halign=halign, valign=valign, margin=8)
    mark.get_style_context().add_class("check")
    mark.set_no_show_all(True)
    mark.set_visible(bool(item["marked"]))
    item["check"] = mark
    return mark


class Grid:
    """Groups of items as tiles or rows in a scrolled box, built CHUNK at a
    time as one nears the end (the first FIRST at once, the rest of the
    first CHUNK in idle steps), SHOWN_MAX at most until «Показать ещё».
    show(groups, rows, keep) takes [(label or None, items)]; with keep the
    page stays where it was scrolled to (within the first SHOWN_MAX). A tap calls opened(item), a long
    press held(item). Tiles come per_line to a line (five beside the panel,
    fewer beside more)."""

    def __init__(self, thumbs, opened, held, per_line=5):
        self.thumbs, self.opened, self.held_cb = thumbs, opened, held
        self.per_line = per_line
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.scroll.add(self.box)
        self.scroll.get_vadjustment().connect("value-changed", self._moved)
        self.groups, self.rows = [], False
        self.gi = self.ii = 0
        self.part = None
        self.built, self.limit = 0, SHOWN_MAX
        self.more_btn = None
        self.held = False
        self.shows = 0  # show() calls; an idle step of an older one stops

    def show(self, groups, rows=False, keep=False):
        adj = self.scroll.get_vadjustment()
        value, built = (adj.get_value(), min(self.built, SHOWN_MAX)) if keep else (0, 0)
        self.limit = SHOWN_MAX
        self.thumbs.reset()
        clear(self.box)
        self.more_btn = None
        self.groups, self.rows = [(lbl, list(items)) for lbl, items in groups], rows
        self.gi = self.ii = 0
        self.part = None
        self.built = 0
        adj.set_value(0)
        self.box.show()
        self.shows += 1
        if value:  # all at once, then scrolled once the new tiles have their sizes
            self.more(max(CHUNK, built))
            GLib.idle_add(self._scroll_to, value)
        else:
            self.more(FIRST)
            if CHUNK > FIRST:
                GLib.idle_add(self._step, self.shows, CHUNK, priority=GLib.PRIORITY_LOW)

    def _step(self, shows, upto):
        """The next FIRST items of a new folder, until upto are built."""
        if shows != self.shows or self.gi >= len(self.groups) or self.built >= min(
                upto, self.limit):
            return False
        self.more(min(FIRST, upto - self.built))
        return True

    def more(self, n):
        """n items more at the end; only the new ones are shown."""
        if self.more_btn:
            self.box.remove(self.more_btn)
            self.more_btn.destroy()
            self.more_btn = None
        n = min(n, self.limit - self.built)
        while n > 0 and self.gi < len(self.groups):
            label, items = self.groups[self.gi]
            if self.ii == 0:
                if label:
                    head = Gtk.Label(label=label, xalign=0)
                    head.get_style_context().add_class("section")
                    self.box.pack_start(head, False, False, 0)
                    head.show()
                self.part = self._part()
                self.box.pack_start(self.part, False, False, 0)
                self.part.show()
            take = items[self.ii:self.ii + n]
            for item in take:
                self._add(item)
            self.ii += len(take)
            self.built += len(take)
            n -= len(take)
            if self.ii >= len(items):
                self.gi, self.ii = self.gi + 1, 0
        if self.gi < len(self.groups) and self.built >= self.limit:
            self.more_btn = Gtk.Button(label="Показать ещё")
            self.more_btn.get_style_context().add_class("more")
            self.more_btn.connect("clicked", lambda _b: self._show_more())
            self.box.pack_start(self.more_btn, False, False, 0)
            self.more_btn.show()

    def _show_more(self):
        self.limit += SHOWN_MAX
        self.more(CHUNK)

    def _scroll_to(self, value):
        self.scroll.get_vadjustment().set_value(value)
        return False

    def _part(self):
        if self.rows:
            part = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            part.connect("row-activated", lambda _l, r: self._tap(r.item))
            press = Gtk.GestureLongPress(widget=part)
            press.connect("pressed", lambda _g, _x, y, p=part: self._hold(
                getattr(p.get_row_at_y(int(y)), "item", None)))
        else:
            part = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               min_children_per_line=self.per_line,
                               max_children_per_line=self.per_line,
                               column_spacing=8, row_spacing=8,
                               valign=Gtk.Align.START)
            part.set_activate_on_single_click(True)
            part.connect("child-activated", lambda _f, c: self._tap(c.item))
            press = Gtk.GestureLongPress(widget=part)
            press.connect("pressed", lambda _g, x, y, p=part: self._hold(
                getattr(p.get_child_at_pos(int(x), int(y)), "item", None)))
        part.press = press  # kept alive with the part
        return part

    def _add(self, item):
        if self.rows:
            row = Gtk.ListBoxRow()
            row.item = item
            row.add(row_box(item, self.thumbs))
            self.part.add(row)
            row.show_all()
        else:
            child = Gtk.FlowBoxChild()
            child.item = item
            child.add(tile(item, self.thumbs))
            self.part.add(child)
            child.show_all()

    def _tap(self, item):
        if self.held:  # the release after a long press opens nothing
            self.held = False
            return
        self.opened(item)

    def _hold(self, item):
        if item is None:
            return
        self.held = True
        GLib.timeout_add(1500, lambda: setattr(self, "held", False))
        self.held_cb(item)

    def _moved(self, adj):
        if adj.get_value() + adj.get_page_size() > adj.get_upper() - 900:
            if self.gi < len(self.groups) and self.built < self.limit:
                self.more(CHUNK)


class Viewer(photos.Viewer):
    """haltia_kit's photo viewer for items: show(items, i), drop(item);
    held(item) on a long press. With win, a big «Отправить» in the corner
    sends the photo shown (when the kit has haltia_kit.share)."""

    def __init__(self, titled, held, win=None):
        self.by_path = {}
        super().__init__(lambda title: titled(shown(title)),
                         lambda path: held(self.by_path.get(path, {"path": path})))
        if win is not None and share is not None:
            button = Gtk.Button(label="Отправить", halign=Gtk.Align.END,
                                valign=Gtk.Align.START)
            button.get_style_context().add_class("send")
            button.connect("clicked", lambda *_a: self.paths and send(
                win, self.paths[self.i]))
            self.add_overlay(button)

    def show(self, items, i=0):
        self.by_path = {x["path"]: x for x in items}
        super().show([x["path"] for x in items], i)

    def drop(self, item):
        return super().drop(item["path"])


class SoundBar(Gtk.Box):
    """Sound files played one after another (haltia_kit.sound.Player, which
    keeps the machine awake while it plays), with the bar at the bottom:
    the title, back, pause, on, stop and a time bar to seek. play(items, i)."""

    def __init__(self, thumbs, failed, player=None):
        super().__init__(spacing=12)
        self.thumbs, self.failed = thumbs, failed
        self.get_style_context().add_class("soundbar")
        self.cover = icon_image("audio", 64)
        self.pack_start(self.cover, False, False, 0)
        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        self.ttl = Gtk.Label(xalign=0, max_width_chars=1)
        self.ttl.set_ellipsize(Pango.EllipsizeMode.END)
        self.ttl.get_style_context().add_class("ttl")
        self.sub = Gtk.Label(xalign=0, max_width_chars=1)
        self.sub.set_ellipsize(Pango.EllipsizeMode.END)
        self.sub.get_style_context().add_class("sub")
        text.pack_start(self.ttl, False, False, 0)
        text.pack_start(self.sub, False, False, 0)
        text.set_size_request(260, -1)
        self.pack_start(text, False, False, 0)
        for label, act in (("⏮", lambda: self.step(-1)), ("❚❚", self.toggle),
                           ("⏭", lambda: self.step(1))):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, a=act: a())
            self.pack_start(b, False, False, 0)
            if label == "❚❚":
                self.pause_btn = b
        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 1)
        self.scale.set_draw_value(False)
        self.scale.connect("change-value", self._seek)
        self.pack_start(self.scale, True, True, 0)
        self.time = Gtk.Label()
        self.time.get_style_context().add_class("sub")
        self.pack_start(self.time, False, False, 0)
        stop = Gtk.Button(label="■")
        stop.connect("clicked", lambda _b: self.stop())
        self.pack_start(stop, False, False, 0)
        self.set_no_show_all(True)
        self.player = player or sound.Player(
            "Файлы", on_end=lambda: self.step(1, True), on_time=self._time,
            on_pause=self._paused, on_error=lambda _t: self.step(1, True))
        self.items, self.i = [], 0
        self.dur = None

    def play(self, items, i):
        self.items, self.i = items, i
        self._start()

    def _start(self):
        item = self.items[self.i]
        try:
            self.player.play(item["path"])
        except RuntimeError as exc:  # no libmpv: say so
            self.failed("Не удалось включить звук: %s" % exc)
            return
        self.ttl.set_text(caption(item))
        self.sub.set_text(item.get("artist") or library.nice_date(item["mtime"]))
        self.cover.set_from_icon_name(ICONS["audio"], Gtk.IconSize.DIALOG)
        self.thumbs.want(item["path"], self.cover, 64)
        self.dur = item.get("duration")
        self.scale.set_range(0, max(1, self.dur or 1))
        self.scale.set_value(0)
        self.pause_btn.set_label("❚❚")
        self.set_no_show_all(False)
        self.show_all()

    def step(self, d, ended=False):
        if not self.items:
            return
        if ended and self.i == len(self.items) - 1:
            self.pause_btn.set_label("▶")
            return
        self.i = (self.i + d) % len(self.items)
        self._start()

    def toggle(self):
        self.player.toggle()

    def pause(self):
        self.player.pause()

    def stop(self):
        self.player.stop()
        self.hide()
        self.set_no_show_all(True)

    def quit(self):
        self.player.quit()

    def _seek(self, _s, _scroll, value):
        self.player.seek(value)
        return False

    def _time(self, v):
        dur = self.dur or self.player.duration
        if dur:
            self.scale.set_range(0, max(1, dur))
        self.scale.set_value(v)
        self.time.set_text("%s / %s" % (library.nice_duration(v), library.nice_duration(dur))
                           if dur else library.nice_duration(v))

    def _paused(self, v):
        self.pause_btn.set_label("▶" if v else "❚❚")
