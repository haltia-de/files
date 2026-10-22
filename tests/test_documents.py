#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Документы' reading.py: opening a PDF made here with cairo, its pages,
turning them, the counter, and the files it refuses.
Run: python3 tests/test_documents.py (needs py3-cairo and poppler-glib;
skipped without them)."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)

try:
    import cairo
    import reading
except (ImportError, ValueError) as exc:  # ValueError: no Poppler typelib
    cairo = reading = None
    MISSING = str(exc)


def make_pdf(path, pages, size=(595, 842)):
    """A PDF of pages pages (A4 in points), each with its number on it."""
    surface = cairo.PDFSurface(path, *size)
    cr = cairo.Context(surface)
    for n in range(pages):
        cr.set_source_rgb(0, 0, 0)
        cr.set_font_size(48)
        cr.move_to(100, 200)
        cr.show_text("Page %d" % (n + 1))
        cr.show_page()
    surface.finish()
    return path


@unittest.skipIf(reading is None, "needs py3-cairo and poppler-glib: %s"
                 % (MISSING if reading is None else ""))
class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)

    def path(self, name):
        return os.path.join(self.dir.name, name)

    def test_open_and_render(self):
        doc = reading.Document(make_pdf(self.path("три.pdf"), 3))
        self.assertEqual(len(doc), 3)
        self.assertEqual(doc.name, "три.pdf")
        w, h = doc.sizes[0]
        self.assertAlmostEqual(w, 595, delta=1)
        self.assertAlmostEqual(h, 842, delta=1)
        surface = doc.render(1, 0.5)
        self.assertEqual((surface.get_width(), surface.get_height()), (298, 421))
        # The page is white with black text on it: not all one colour.
        data = bytes(surface.get_data())
        self.assertGreater(len({data[i:i + 4] for i in range(0, len(data), 4)}), 1)

    def test_huge_scale_is_bounded(self):
        doc = reading.Document(make_pdf(self.path("a.pdf"), 1))
        surface = doc.render(0, 100)
        self.assertLessEqual(surface.get_width() * surface.get_height(),
                             reading.MAX_PIXELS * 1.01)

    def test_pages_kept(self):
        doc = reading.Document(make_pdf(self.path("five.pdf"), 5))
        pages = reading.Pages(doc, kept=2)
        self.assertIsNone(pages.peek(0, 1.0))
        first = pages.get(0, 1.0)
        self.assertIs(pages.get(0, 1.0), first)
        self.assertIs(pages.peek(0, 1.0), first)
        pages.get(1, 1.0)
        pages.get(2, 1.0)
        self.assertEqual(len(pages.pages), 2)
        self.assertIsNone(pages.peek(0, 1.0))  # the oldest went
        self.assertIsNotNone(pages.peek(2, 1.0))

    def test_turning_and_counter(self):
        doc = reading.Document(make_pdf(self.path("twelve.pdf"), 12))
        reader = reading.Reader(len(doc))
        self.assertEqual(reader.counter(), "стр. 1 из 12")
        self.assertFalse(reader.can_turn(-1))
        self.assertFalse(reader.turn(-1))
        self.assertEqual(reader.page, 0)
        self.assertTrue(reader.turn(1))
        self.assertTrue(reader.turn(1))
        self.assertEqual(reader.counter(), "стр. 3 из 12")
        for _i in range(20):
            reader.turn(1)
        self.assertEqual(reader.counter(), "стр. 12 из 12")
        self.assertFalse(reader.can_turn(1))
        self.assertTrue(reader.turn(-1))
        self.assertEqual(reader.counter(), "стр. 11 из 12")

    def test_zoom(self):
        reader = reading.Reader(1)
        self.assertIsNone(reader.zoom)  # «по ширине» at first
        self.assertAlmostEqual(reader.scale(600, 1200), 2.0)
        reader.zoom_to(3.0)
        self.assertEqual(reader.scale(600, 1200), 3.0)
        reader.zoom_to(100)
        self.assertEqual(reader.zoom, reading.ZOOM_MAX)
        reader.zoom_to(0)
        self.assertEqual(reader.zoom, reading.ZOOM_MIN)
        reader.fit()
        self.assertAlmostEqual(reader.scale(600, 600), 1.0)

    def refused(self, path, words):
        with self.assertRaises(reading.Refused) as caught:
            reading.Document(path)
        self.assertIn(words, str(caught.exception))

    def test_broken(self):
        good = make_pdf(self.path("good.pdf"), 2)
        with open(good, "rb") as fh:
            head = fh.read(200)
        with open(self.path("broken.pdf"), "wb") as fh:
            fh.write(head)  # cut off: no pages, no cross-reference table
        self.refused(self.path("broken.pdf"), "повреждён")

    def test_not_pdf(self):
        with open(self.path("note.pdf"), "w") as fh:
            fh.write("just text\n")
        self.refused(self.path("note.pdf"), "не PDF")
        with open(self.path("empty.pdf"), "wb"):
            pass
        self.refused(self.path("empty.pdf"), "не PDF")

    def test_missing(self):
        self.refused(self.path("nowhere.pdf"), "Не удалось открыть")


class BackTests(unittest.TestCase):
    def test_back_stays_off(self):
        """One screen: app.back is never enabled, so the shell shows «домой»."""
        with open(os.path.join(HERE, "haltia-documents"), encoding="utf-8") as fh:
            source = fh.read()
        self.assertIn('Gio.SimpleAction.new("back", None)', source)
        self.assertIn("self.back_action.set_enabled(False)", source)
        self.assertNotIn("set_enabled(True)", source)


if __name__ == "__main__":
    unittest.main()
