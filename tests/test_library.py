#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""The media library: finding, kinds, grouping.
Run: python3 tests/test_library.py (needs PyGObject with GdkPixbuf and
haltia-kit, installed or checked out next to this repository as kit/)."""
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
for _kit in ("kit", "b8k-compat"):
    if os.path.isdir(os.path.join(os.path.dirname(HERE), _kit, "haltia_kit")):
        sys.path.insert(0, os.path.join(os.path.dirname(HERE), _kit))
        break
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp()
import gi  # noqa: E402

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf  # noqa: E402

import library  # noqa: E402

top = tempfile.mkdtemp()
home, cache = os.path.join(top, "home"), os.path.join(top, "cache")


def put(rel, data=b"x", mtime=None):
    path = os.path.join(home, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


def photo(rel, w, h, mtime=None):
    path = os.path.join(home, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, w, h)
    pix.fill(0x3584e4ff)
    pix.savev(path, "png", [], [])
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


assert library.kind_of("a.JPG") == "photo" and library.kind_of("b.mkv") == "video"
assert library.kind_of("c.opus") == "audio" and library.kind_of("d.txt") is None
assert library.kind_of("noext") is None

oct17 = time.mktime((2026, 10, 17, 12, 0, 0, 0, 0, -1))
sep3 = time.mktime((2026, 9, 3, 12, 0, 0, 0, 0, -1))
p1 = photo("Downloads/MAX/photo.png", 400, 300, oct17)
p2 = photo("Раскраски/кот.png", 300, 600, sep3)
v1 = put("Видео/clip.mp4", b"not a real video", oct17 - 60)
a1 = put("Музыка/song.mp3", b"not a real song", sep3 - 60)
put(".cache/hidden.jpg")  # hidden folders are not searched
put("Documents/notes.txt")  # not media
put("Downloads/empty.jpg", b"")  # empty files are left out

lib = library.Library(home, cache, roots=[home])
assert not lib.load()
assert lib.scan() is True
assert {i["path"] for i in lib.items()} == {p1, p2, v1, a1}
assert [i["path"] for i in lib.items()] == [p1, v1, p2, a1]  # newest first
assert [i["path"] for i in lib.items("photo")] == [p1, p2]
assert lib.counts() == {"all": 4, "photo": 2, "video": 1, "audio": 1}
assert "duration" in lib.items("video")[0]  # asked (None: not a real video)
assert lib.scan() is False  # nothing changed
print("scan ok")

lib2 = library.Library(home, cache, roots=[home])
assert lib2.load() and len(lib2.items()) == 4  # the index on disk, at once
put("Видео/clip.mp4", b"another length", oct17)
assert lib2.scan() is True and lib2.items("video")[0]["size"] == len(b"another length")
print("index ok")

months = library.Library.by_month(lib.items())
assert [m for m, _ in months] == ["Октябрь 2026", "Сентябрь 2026"]
assert [i["path"] for i in months[0][1]] == [p1, v1]
folders = lib.by_folder(lib.items())
assert [label for label, _f, _i in folders] == ["Downloads/MAX", "Видео", "Раскраски", "Музыка"]
assert lib.folder_label(home) == "Дом"
print("groups ok")


lib.forget(lib.items("photo")[0])
assert lib.counts()["photo"] == 1
assert library.nice_duration(65) == "1:05" and library.nice_duration(3725) == "1:02:05"
assert library.nice_size(2048) == "2.0 КБ"
assert library.files_word(1) == "1 файл" and library.files_word(3) == "3 файла"
assert library.files_word(11) == "11 файлов"
assert library.nice_date(oct17, now=oct17) == "17 окт"
print("all passed")
