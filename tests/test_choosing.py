#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""The file chooser's decisions (choosing.py): filters, the folder to start
in, free names, recent files, dates in words.
Run: python3 tests/test_choosing.py (needs PyGObject and haltia-kit,
installed or checked out next to this repository as kit/)."""
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

import choosing  # noqa: E402

home = tempfile.mkdtemp()
for d in ("Документы", "Загрузки", "Изображения", "Музыка"):
    os.makedirs(os.path.join(home, d))


def put(rel, mtime=None):
    path = os.path.join(home, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").close()
    if mtime:
        os.utime(path, (mtime, mtime))
    return path


photos = ("Фото", [(0, "*.jpg"), (0, "*.JPG"), (1, "image/png")])
pictures = ("Картинки", [(1, "image/jpeg"), (1, "image/png"), (1, "image/webp")])
everything = ("Все файлы", [(0, "*")])

# Filters: globs are case-sensitive as GTK's are, mime types by the name.
assert choosing.matches("кот.jpg", photos)
assert choosing.matches("кот.JPG", photos)
assert choosing.matches("кот.png", photos)
assert not choosing.matches("кот.Jpg", photos)
assert not choosing.matches("отчёт.pdf", photos)
assert choosing.matches("кот.jpeg", pictures)
assert choosing.matches("что-угодно", everything)
assert choosing.matches("что-угодно", None)
assert choosing.matches("a.png", ("Картинки", [(1, "image/*")]))

# A filter's kind of file decides the folder; «Все файлы» decides nothing.
assert choosing.filter_kind(photos) == "photo"
assert choosing.filter_kind(pictures) == "photo"
assert choosing.filter_kind(everything) is None
assert choosing.filter_kind(("Музыка", [(1, "audio/mpeg"), (0, "*.ogg")])) == "audio"
assert choosing.filter_kind(("Смесь", [(1, "audio/mpeg"), (1, "image/png")])) is None

# Where to start: the program's folder, the filter's kind, the last one, Загрузки.
docs = os.path.join(home, "Документы")
pics = os.path.join(home, "Изображения")
dl = os.path.join(home, "Загрузки")
assert choosing.start_folder(docs, photos, None, home) == docs
assert choosing.start_folder(None, photos, docs, home) == pics
assert choosing.start_folder(None, everything, docs, home) == docs
assert choosing.start_folder("/нет/такой", everything, "/и/такой", home) == dl
assert choosing.start_folder(None, ("Видео", [(1, "video/mp4")]), None, home) == dl  # no Видео

# Saving: by kind, the program's folder first; a taken name gets (2), (3).
assert choosing.save_folder("кот.png", None, home) == pics
assert choosing.save_folder("письмо.pdf", None, home) == docs
assert choosing.save_folder("архив.zip", None, home) == dl
assert choosing.save_folder("кот.png", dl, home) == dl
assert choosing.free_name(dl, "кот.png") == "кот.png"
put("Загрузки/кот.png")
assert choosing.free_name(dl, "кот.png") == "кот (2).png"
put("Загрузки/кот (2).png")
assert choosing.free_name(dl, "кот.png") == "кот (3).png"
put("Загрузки/дом.tar.gz")
assert choosing.free_name(dl, "дом.tar.gz") == "дом (2).tar.gz"
put("Загрузки/.bashrc")
assert choosing.free_name(dl, ".bashrc") == ".bashrc (2)"
assert choosing.free_name(dl, "a/b") == "ab"
assert choosing.free_name(dl, "").startswith("Файл ")
assert choosing.new_name(time.mktime((2026, 10, 20, 16, 5, 0, 0, 0, -1))) == "Файл 20 октября 16-05"

# A folder: folders first by name, files that pass newest first, no hidden ones.
now = time.time()
put("Изображения/старый.jpg", now - 86400 * 3)
put("Изображения/новый.jpg", now - 60)
put("Изображения/список.txt", now - 30)
put("Изображения/.скрытый.jpg", now)
os.makedirs(os.path.join(pics, "Альбом"))
names = [e[1] for e in choosing.listing(pics, photos)]
assert names == ["Альбом", "новый.jpg", "старый.jpg"], names
assert [e[1] for e in choosing.listing(pics, None, folders_only=True)] == ["Альбом"]
assert ".скрытый.jpg" in [e[1] for e in choosing.listing(pics, None, hidden=True)]
assert choosing.listing(os.path.join(home, "нет")) is None
assert choosing.media_share(choosing.listing(pics, photos)) == 1.0
assert choosing.media_share(choosing.listing(pics, None)) == 2 / 3

# Recent: the newest files of all folders that pass, within the days.
put("Загрузки/MAX/снимок.jpg", now - 120)
put("Документы/давнее.jpg", now - 86400 * 90)
rec = [e[1] for e in choosing.recent([docs, dl, pics], ("JPEG", [(0, "*.jpg")]), now)]
assert rec == ["новый.jpg", "снимок.jpg", "старый.jpg"], rec

# Places: the user's folders that exist; the helper's switch adds home and system.
labels = [p[0] for p in choosing.places(False, home)]
assert labels[:4] == ["Документы", "Загрузки", "Изображения", "Музыка"], labels
full = [p[0] for p in choosing.places(True, home)]
assert full[0] == "Дом" and full[-1] == "Система"
assert choosing.card_label("mmcblk1p1") == "Карта памяти"
assert choosing.card_label("KINGSTON") == "Флешка"

# Dates in words.
noon = time.mktime((2026, 10, 20, 12, 0, 0, 0, 0, -1))
assert choosing.when(noon - 3600 * 2, noon) == "сегодня, 10:00"
assert choosing.when(noon - 86400, noon) == "вчера, 12:00"
assert choosing.when(noon - 86400 * 8, noon) == "12 окт"
assert choosing.when(time.mktime((2025, 3, 1, 9, 0, 0, 0, 0, -1)), noon) == "1 мар 2025"

# Portal paths are NUL-terminated bytes.
assert choosing.as_path(b"/home/user\0") == "/home/user"
assert choosing.as_path(list(b"/tmp\0")) == "/tmp"
assert choosing.as_path(None) is None

print("ok")
