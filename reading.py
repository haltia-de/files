# SPDX-License-Identifier: GPL-2.0
"""What Документы (haltia-documents) decides, without GTK: opening a PDF
with poppler-glib (open_document), its pages rendered to cairo surfaces and
kept a few at a time (Pages), and which page is shown how large (Reader).
Rendering blocks: the window calls Pages.get from a thread.
"""
import collections
import math
import os
import threading

import cairo
import gi

gi.require_version("Poppler", "0.18")
from gi.repository import Gio, GLib, Poppler  # noqa: E402

PAGES_KEPT = 3  # rendered pages in memory: the one shown and its neighbours
MAX_PIXELS = 8 * 1024 * 1024  # a page is never rendered larger than this
ZOOM_MIN, ZOOM_MAX, ZOOM_STEP = 0.25, 4.0, 1.25


class Refused(Exception):
    """A file that is not opened; str() is what the window says."""


def is_pdf(path):
    """A PDF by its first bytes, whatever its name."""
    with open(path, "rb") as fh:
        return b"%PDF-" in fh.read(1024)


class Document:
    """An open PDF: len(), sizes[i] (points) and render(i, scale). Poppler
    is used by one thread at a time (Pages holds the lock)."""

    def __init__(self, path):
        self.path = path
        self.name = GLib.filename_display_name(os.path.basename(path))
        try:
            pdf = is_pdf(path)
        except OSError as exc:
            raise Refused("Не удалось открыть: %s" % exc.strerror)
        if not pdf:
            raise Refused("Это не PDF-документ, «Документы» его не откроют.")
        try:
            self.doc = Poppler.Document.new_from_file(Gio.File.new_for_path(path).get_uri(),
                                                      None)
        except GLib.Error as exc:
            if exc.matches(Poppler.error_quark(), Poppler.Error.ENCRYPTED):
                raise Refused("Документ защищён паролем")
            raise Refused("Документ повреждён и не открывается.")
        self.sizes = [self.doc.get_page(i).get_size() for i in range(self.doc.get_n_pages())]
        if not self.sizes:
            raise Refused("Документ повреждён: в нём нет страниц.")

    def __len__(self):
        return len(self.sizes)

    def render(self, i, scale):
        """Page i as an image surface, scale pixels a point (less for a page
        that would exceed MAX_PIXELS)."""
        w, h = self.sizes[i]
        scale = min(scale, math.sqrt(MAX_PIXELS / max(1.0, w * h)))
        surface = cairo.ImageSurface(cairo.FORMAT_RGB24, max(1, int(math.ceil(w * scale))),
                                     max(1, int(math.ceil(h * scale))))
        cr = cairo.Context(surface)
        cr.set_source_rgb(1, 1, 1)
        cr.paint()
        cr.scale(scale, scale)
        self.doc.get_page(i).render(cr)
        surface.flush()
        return surface


class Pages:
    """Rendered pages, PAGES_KEPT at most, the oldest dropped first:
    get(i, scale) renders what is not kept (blocking), peek only looks."""

    def __init__(self, document, kept=PAGES_KEPT):
        self.document, self.kept = document, kept
        self.pages = collections.OrderedDict()
        self.lock = threading.Lock()

    @staticmethod
    def key(i, scale):
        return i, round(scale, 3)

    def peek(self, i, scale):
        with self.lock:
            return self.pages.get(self.key(i, scale))

    def get(self, i, scale):
        key = self.key(i, scale)
        with self.lock:
            if key in self.pages:
                self.pages.move_to_end(key)
                return self.pages[key]
            surface = self.document.render(i, key[1])
            self.pages[key] = surface
            while len(self.pages) > self.kept:
                self.pages.popitem(last=False)
            return surface


class Reader:
    """The page shown (0-based) of n and the zoom: None is «по ширине»,
    else pixels a point."""

    def __init__(self, n):
        self.n, self.page, self.zoom = n, 0, None

    def counter(self):
        return "стр. %d из %d" % (self.page + 1, self.n)

    def can_turn(self, d):
        return 0 <= self.page + d < self.n

    def turn(self, d):
        """True when the page changed."""
        if not self.can_turn(d):
            return False
        self.page += d
        return True

    def scale(self, page_width, width):
        """Pixels a point for a page page_width points wide in a view width
        pixels wide."""
        if self.zoom is None:
            return max(ZOOM_MIN, width / max(1.0, page_width))
        return self.zoom

    def zoom_to(self, scale):
        self.zoom = min(ZOOM_MAX, max(ZOOM_MIN, scale))

    def fit(self):
        self.zoom = None
