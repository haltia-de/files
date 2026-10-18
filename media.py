# SPDX-License-Identifier: GPL-2.0
"""What Файлы and Галерея share for media: small pictures loaded in a
thread (Thumbs), tiles and rows that show them, a grid that is built as
one scrolls (Grid), the photo viewer (Viewer) and the sound bar at the
bottom (SoundBar).

Taps only: the tablet's touch filter passes one finger and drops a second
tap within 400 ms, so there is no pinch and no double tap; the viewer
zooms with its + and − buttons, pans by dragging, and goes to the next or
previous photo by a swipe or ‹ ›.
"""
import os
import queue
import threading

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, Pango  # noqa: E402

import library  # noqa: E402

TILE = 208  # px of a tile's picture; five fit beside the panel
ROW_PIC = 88
CHUNK = 60  # tiles added at a time, more as one scrolls near the end
SLIDE_S = 4
ICONS = {"photo": "image-x-generic", "video": "video-x-generic", "audio": "audio-x-generic",
         "folder": "folder"}

CSS = b"""
.tile { background-color: #f2f2f0; border-radius: 12px; }
.tile label.cap { font-size: 18px; color: #2e3436; }
.tile label.badge { background-color: rgba(0,0,0,0.6); color: #ffffff; font-size: 17px;
  border-radius: 8px; padding: 2px 8px; }
flowboxchild { padding: 0; border-radius: 12px; }
flowboxchild:active { background-color: #c4dcf7; }
label.section { font-size: 26px; font-weight: bold; color: #2e3436; margin: 12px 4px 4px 4px; }
.viewer { background-color: #000000; }
.viewer label.note { color: #ffffff; font-size: 24px; }
.vbar { background-color: rgba(0,0,0,0.55); border-radius: 18px; padding: 8px; }
.vbar button { background-image: none; background-color: rgba(255,255,255,0.18);
  color: #ffffff; border: none; box-shadow: none; border-radius: 14px;
  min-height: 64px; min-width: 76px; font-size: 26px; }
.vbar button.on { background-color: #3584e4; }
.vbar label { color: #ffffff; font-size: 20px; margin: 0 8px; }
.soundbar { background-color: #dcdcda; padding: 8px 16px; }
.soundbar label.ttl { font-size: 22px; font-weight: bold; color: #2e3436; }
.soundbar label.sub { font-size: 18px; color: #5e5c64; }
.soundbar button { background-image: none; background-color: #f2f2f0; color: #2e3436;
  border: 1px solid #c0bfbc; box-shadow: none; border-radius: 14px;
  min-height: 64px; min-width: 72px; font-size: 26px; }
.soundbar scale { min-height: 40px; }
"""


def clear(box):
    for child in box.get_children():
        box.remove(child)
        child.destroy()


class Thumbs:
    """Small pictures from Library.thumb, made and read in one thread, set
    on the GTK side. reset() forgets the requests of a page gone."""

    def __init__(self, lib):
        self.lib = lib
        self.jobs = queue.Queue()
        self.gen = 0
        self.memo = {}  # (path, size) -> pixbuf, the latest few hundred
        threading.Thread(target=self._work, daemon=True).start()

    def reset(self):
        self.gen += 1

    def want(self, item, image, size):
        key = (item["path"], size)
        if key in self.memo:
            image.set_from_pixbuf(self.memo[key])
            return
        self.jobs.put((self.gen, item, image, size))

    def _work(self):
        while True:
            gen, item, image, size = self.jobs.get()
            if gen != self.gen:
                continue
            path = self.lib.thumb(item)
            if not path:
                continue
            try:
                pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, size, size, True)
            except GLib.Error:
                continue
            GLib.idle_add(self._set, gen, item, image, size, pix)

    def _set(self, gen, item, image, size, pix):
        if len(self.memo) > 600:
            self.memo.clear()
        self.memo[(item["path"], size)] = pix
        if gen == self.gen:
            image.set_from_pixbuf(pix)
        return False


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


def caption(item):
    if item["kind"] == "audio" and item.get("title"):
        return item["title"]
    return os.path.basename(item["path"])


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
    box.pack_start(over, False, False, 0)
    if item["kind"] != "photo" or item.get("label"):
        cap = Gtk.Label(label=item.get("label") or caption(item), max_width_chars=1)
        cap.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
        cap.set_size_request(size, -1)
        cap.get_style_context().add_class("cap")
        box.pack_start(cap, False, False, 4)
    want(thumbs, item, image, size)
    return box


def want(thumbs, item, image, size):
    if item["kind"] in library.KINDS:
        thumbs.want(item, image, size)
    elif item.get("cover"):
        thumbs.want(item["cover"], image, size)


def row_box(item, thumbs, sub=None):
    box = Gtk.Box(spacing=16)
    image = icon_image(item, ROW_PIC)
    want(thumbs, item, image, ROW_PIC)
    box.pack_start(image, False, False, 0)
    text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
    name = Gtk.Label(label=item.get("label") or caption(item), xalign=0)
    name.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    name.get_style_context().add_class("name")
    text.pack_start(name, False, False, 0)
    small = Gtk.Label(label=sub if sub is not None else subline(item), xalign=0)
    small.set_ellipsize(Pango.EllipsizeMode.END)
    small.get_style_context().add_class("sub")
    text.pack_start(small, False, False, 0)
    box.pack_start(text, True, True, 0)
    return box


class Grid:
    """Groups of items as tiles or rows in a scrolled box, built CHUNK at a
    time as one nears the end. show(groups, rows) takes [(label or None,
    items)]; a tap calls opened(item), a long press held(item)."""

    def __init__(self, thumbs, opened, held):
        self.thumbs, self.opened, self.held_cb = thumbs, opened, held
        self.scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.scroll.add(self.box)
        self.scroll.get_vadjustment().connect("value-changed", self._moved)
        self.groups, self.rows = [], False
        self.gi = self.ii = 0
        self.part = None
        self.held = False

    def show(self, groups, rows=False):
        self.thumbs.reset()
        clear(self.box)
        self.groups, self.rows = [(lbl, list(items)) for lbl, items in groups], rows
        self.gi = self.ii = 0
        self.part = None
        self.scroll.get_vadjustment().set_value(0)
        self.more(CHUNK)

    def more(self, n):
        while n > 0 and self.gi < len(self.groups):
            label, items = self.groups[self.gi]
            if self.ii == 0:
                if label:
                    head = Gtk.Label(label=label, xalign=0)
                    head.get_style_context().add_class("section")
                    self.box.pack_start(head, False, False, 0)
                self.part = self._part()
                self.box.pack_start(self.part, False, False, 0)
            take = items[self.ii:self.ii + n]
            for item in take:
                self._add(item)
            self.ii += len(take)
            n -= len(take)
            if self.ii >= len(items):
                self.gi, self.ii = self.gi + 1, 0
        self.box.show_all()

    def _part(self):
        if self.rows:
            part = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            part.connect("row-activated", lambda _l, r: self._tap(r.item))
            press = Gtk.GestureLongPress(widget=part)
            press.connect("pressed", lambda _g, _x, y, p=part: self._hold(
                getattr(p.get_row_at_y(int(y)), "item", None)))
        else:
            part = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               min_children_per_line=5, max_children_per_line=5,
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
        else:
            child = Gtk.FlowBoxChild()
            child.item = item
            child.add(tile(item, self.thumbs))
            self.part.add(child)

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
            if self.gi < len(self.groups):
                self.more(CHUNK)


class Viewer(Gtk.Overlay):
    """Photos one at a time on black: ‹ › and a swipe go through them, + −
    zoom and a drag pans, ▶ shows them on by themselves. show(items, i);
    titled(name) tells the window; held(item) on a long press."""

    def __init__(self, titled, held):
        super().__init__()
        self.titled, self.held_cb = titled, held
        self.get_style_context().add_class("viewer")
        self.area = Gtk.DrawingArea()
        self.area.connect("draw", self._draw)
        self.add(self.area)
        self.note = Gtk.Label(halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        self.note.get_style_context().add_class("note")
        self.add_overlay(self.note)
        bar = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER, valign=Gtk.Align.END,
                      margin_bottom=16)
        bar.get_style_context().add_class("vbar")
        self.btn = {}
        for key, text, act in (("prev", "‹", lambda: self.step(-1)),
                               ("out", "−", lambda: self.zoom_by(1 / 1.5)),
                               ("in", "+", lambda: self.zoom_by(1.5)),
                               ("slide", "▶", self.toggle_slides),
                               ("next", "›", lambda: self.step(1))):
            b = Gtk.Button(label=text)
            b.connect("clicked", lambda _b, a=act: a())
            bar.pack_start(b, False, False, 0)
            self.btn[key] = b
            if key == "in":
                self.count = Gtk.Label()
                bar.pack_start(self.count, False, False, 0)
        self.add_overlay(bar)
        self.items, self.i = [], 0
        self.pix = None
        self.zoom, self.dx, self.dy = 1.0, 0.0, 0.0
        self.loading = 0
        self.slides = 0
        drag = Gtk.GestureDrag(widget=self.area)
        drag.connect("drag-begin", self._begin)
        drag.connect("drag-update", self._update)
        drag.connect("drag-end", self._end)
        hold = Gtk.GestureLongPress(widget=self.area)
        hold.connect("pressed", lambda *_a: self.items and self.held_cb(self.items[self.i]))
        self.gestures = (drag, hold)
        self.area.add_events(Gdk.EventMask.TOUCH_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)

    def show(self, items, i):
        self.items, self.i = items, i
        self._load()

    def close(self):
        self.stop_slides()
        self.pix = None
        self.items = []
        self.loading += 1

    def step(self, d):
        if not self.items:
            return
        self.i = (self.i + d) % len(self.items)
        self._load()

    def drop(self, item):
        """A photo deleted: the next one, or none left."""
        self.items = [x for x in self.items if x["path"] != item["path"]]
        if not self.items:
            return False
        self.i = min(self.i, len(self.items) - 1)
        self._load()
        return True

    def _load(self):
        item = self.items[self.i]
        self.loading += 1
        token = self.loading
        self.zoom, self.dx, self.dy = 1.0, 0.0, 0.0
        self.count.set_text("%d из %d" % (self.i + 1, len(self.items)))
        self.titled(os.path.basename(item["path"]))
        self.note.set_text("Открываю…" if self.pix is None else "")
        alloc = self.area.get_allocation()
        side = max(alloc.width, alloc.height, 800) * 2

        def work():
            try:
                pix = library.pixbuf_of(item["path"], side)
            except (GLib.Error, ValueError):
                pix = None
            GLib.idle_add(self._loaded, token, pix)

        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, token, pix):
        if token != self.loading:
            return False
        self.pix = pix
        self.note.set_text("" if pix else "Не удалось открыть картинку.")
        self.area.queue_draw()
        return False

    def _fit(self):
        alloc = self.area.get_allocation()
        w, h = self.pix.get_width(), self.pix.get_height()
        return min(alloc.width / w, alloc.height / h), alloc.width, alloc.height

    def _draw(self, _w, cr):
        cr.set_source_rgb(0, 0, 0)
        cr.paint()
        if not self.pix:
            return
        fit, aw, ah = self._fit()
        k = fit * self.zoom
        w, h = self.pix.get_width() * k, self.pix.get_height() * k
        self._clamp(w, h, aw, ah)
        cr.translate((aw - w) / 2 + self.dx, (ah - h) / 2 + self.dy)
        cr.scale(k, k)
        Gdk.cairo_set_source_pixbuf(cr, self.pix, 0, 0)
        cr.paint()

    def _clamp(self, w, h, aw, ah):
        mx, my = max(0, (w - aw) / 2), max(0, (h - ah) / 2)
        self.dx = min(mx, max(-mx, self.dx))
        self.dy = min(my, max(-my, self.dy))

    def zoom_by(self, f):
        if not self.pix:
            return
        self.zoom = min(4.0, max(1.0, self.zoom * f))
        if self.zoom == 1.0:
            self.dx = self.dy = 0.0
        self.area.queue_draw()

    def _begin(self, _g, _x, _y):
        self.stop_slides()
        self.start = (self.dx, self.dy)

    def _update(self, _g, ox, oy):
        if self.zoom > 1.0:
            self.dx, self.dy = self.start[0] + ox, self.start[1] + oy
            self.area.queue_draw()

    def _end(self, _g, ox, oy):
        if self.zoom == 1.0 and abs(ox) > 100 and abs(ox) > 2 * abs(oy):
            self.step(-1 if ox > 0 else 1)

    def toggle_slides(self):
        if self.slides:
            self.stop_slides()
            return
        self.btn["slide"].get_style_context().add_class("on")
        self.btn["slide"].set_label("❚❚")
        self.slides = GLib.timeout_add_seconds(SLIDE_S, self._slide)

    def _slide(self):
        self.step(1)
        return True

    def stop_slides(self):
        if self.slides:
            GLib.source_remove(self.slides)
            self.slides = 0
            self.btn["slide"].get_style_context().remove_class("on")
            self.btn["slide"].set_label("▶")


class SoundBar(Gtk.Box):
    """Sound files played here, one after another, with the bar at the
    bottom: the title, back, pause, on, stop and a time bar to seek.
    play(items, i). While it plays, $XDG_RUNTIME_DIR/b8k-awake/<pid>.suspend
    keeps the tablet from sleeping when the screen goes off."""

    def __init__(self, thumbs, failed):
        super().__init__(spacing=12)
        self.thumbs, self.failed = thumbs, failed
        self.get_style_context().add_class("soundbar")
        self.cover = icon_image("audio", 64)
        self.dur = None
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
        self.mpv = None
        self.items, self.i = [], 0
        self.awake = None
        run = os.environ.get("XDG_RUNTIME_DIR")
        if run:
            self.awake = os.path.join(run, "b8k-awake", "%d.suspend" % os.getpid())

    def _player(self):
        if self.mpv is None:
            import mpv

            self.mpv = mpv.MPV(video=False, ytdl=False, input_default_bindings=False,
                               terminal=False)
            self.mpv.observe_property("time-pos", lambda _n, v: GLib.idle_add(self._time, v))
            self.mpv.observe_property("pause", lambda _n, v: GLib.idle_add(self._paused, v))

            @self.mpv.event_callback("end-file")
            def _end(event):
                reason = str(getattr(getattr(event, "data", None), "reason", ""))
                if reason in ("0", "eof", "b'eof'") or reason.endswith("EOF"):
                    GLib.idle_add(self.step, 1, True)
        return self.mpv

    def play(self, items, i):
        self.items, self.i = items, i
        self._start()

    def _start(self):
        item = self.items[self.i]
        try:
            player = self._player()
            player.play(item["path"])
            player.pause = False
        except Exception as exc:  # no libmpv: say so
            self.failed("Не удалось включить звук: %s" % exc)
            return
        self.ttl.set_text(caption(item))
        self.sub.set_text(item.get("artist") or library.nice_date(item["mtime"]))
        self.cover.set_from_icon_name(ICONS["audio"], Gtk.IconSize.DIALOG)
        self.thumbs.want(item, self.cover, 64)
        dur = item.get("duration") or 1
        self.scale.set_range(0, max(1, dur))
        self.scale.set_value(0)
        self.dur = item.get("duration")
        self.set_no_show_all(False)
        self.show_all()
        self._awake(True)

    def step(self, d, ended=False):
        if not self.items:
            return False
        if ended and self.i == len(self.items) - 1:
            self._awake(False)
            self.pause_btn.set_label("▶")
            return False
        self.i = (self.i + d) % len(self.items)
        self._start()
        return False

    def toggle(self):
        if self.mpv is not None:
            self.mpv.pause = not self.mpv.pause

    def pause(self):
        if self.mpv is not None:
            self.mpv.pause = True

    def stop(self):
        if self.mpv is not None:
            try:
                self.mpv.stop()
            except Exception:
                pass
        self._awake(False)
        self.hide()
        self.set_no_show_all(True)

    def quit(self):
        self.stop()
        if self.mpv is not None:
            try:
                self.mpv.terminate()
            except Exception:
                pass
            self.mpv = None

    def _seek(self, _s, _scroll, value):
        if self.mpv is not None:
            try:
                self.mpv.seek(max(0, value), reference="absolute")
            except Exception:
                pass
        return False

    def _time(self, v):
        if v is None:
            return False
        try:
            dur = self.dur or self.mpv.duration
        except Exception:
            dur = self.dur
        if dur:
            self.scale.set_range(0, max(1, dur))
        self.scale.set_value(v)
        self.time.set_text("%s / %s" % (library.nice_duration(v), library.nice_duration(dur))
                           if dur else library.nice_duration(v))
        return False

    def _paused(self, v):
        self.pause_btn.set_label("▶" if v else "❚❚")
        self._awake(not v)
        return False

    def _awake(self, on):
        if not self.awake:
            return
        try:
            if on:
                os.makedirs(os.path.dirname(self.awake), mode=0o700, exist_ok=True)
                open(self.awake, "w").close()
            elif os.path.exists(self.awake):
                os.unlink(self.awake)
        except OSError:
            pass

