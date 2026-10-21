# SPDX-License-Identifier: GPL-2.0
"""The media library of Галерея (haltia-files --gallery): every photo, video
and sound file kept on the tablet, and how it is grouped. Files are read
(lengths, tags) through haltia-kit, in its memory-capped reader process.

Library(home, cache) is the one interface the window uses:

  load()          what was found last time (the index on disk), at once
  scan()          walk the home folder and the memory cards again; reuses
                  what is known of a file whose size and time are the same;
                  returns True when anything changed (blocking: a thread)
  items(kind)     the files of a kind ("all", "photo", "video", "audio"),
                  newest first
  counts()        how many of each kind
  by_month(items) [(label, items)] by the month the file was made
  by_folder(items) [(label, folder, items)] by folder, newest first
  forget(item)    take a deleted file out

An item is a dict: path, kind, size, mtime, and for video and sound
duration (seconds or None), for sound title and artist when tagged. Hidden
folders (.cache, .local, ...) are not searched. Small pictures are
haltia-kit's freedesktop thumbnails (haltia_kit.photos).
"""
import json
import os
import threading

from haltia_kit.formats import month, nice_date, nice_duration, nice_size, plural  # noqa: F401
from haltia_kit.photos import kind_of, media_info

KINDS = ("photo", "video", "audio")
LIMIT = 30000  # files at most, so a huge card cannot eat the memory
DEPTH = 12


def files_word(n):
    return plural(n, "файл", "файла", "файлов")


def card_roots(user):
    """Memory cards and USB sticks mounted for the session."""
    out = []
    for base in ("/media", "/run/media/" + user):
        try:
            for entry in os.scandir(base):
                if entry.is_dir() and os.path.ismount(entry.path):
                    out.append(entry.path)
        except OSError:
            pass
    return out


def walk(roots, limit=LIMIT):
    """(path, size, mtime) of every media file under roots, hidden folders
    and symlinked folders left out."""
    found, seen = [], set()
    stack = [(r, 0) for r in roots]
    while stack and len(found) < limit:
        folder, depth = stack.pop()
        try:
            real = os.path.realpath(folder)
            if real in seen:
                continue
            seen.add(real)
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if depth < DEPTH:
                        stack.append((e.path, depth + 1))
                elif e.is_file() and kind_of(e.name):
                    st = e.stat()
                    if st.st_size > 0:
                        found.append((e.path, st.st_size, st.st_mtime))
            except OSError:
                continue
    return found


class Library:
    def __init__(self, home, cache, user=None, roots=None):
        self.home = home
        self.cache = cache
        self.user = user or os.environ.get("USER", "")
        self.roots = roots
        self.index_path = os.path.join(cache, "index.json")
        self.known = {}  # path -> item
        self.lock = threading.Lock()

    # --- the index -------------------------------------------------------
    def load(self):
        try:
            with open(self.index_path, encoding="utf-8") as fh:
                data = json.load(fh)
            items = {i["path"]: i for i in data.get("items", []) if kind_of(i["path"])}
        except (OSError, ValueError, KeyError, TypeError):
            items = {}
        with self.lock:
            self.known = items
        return bool(items)

    def save(self):
        os.makedirs(self.cache, mode=0o700, exist_ok=True)
        with self.lock:
            items = list(self.known.values())
        tmp = self.index_path + ".new"
        with open(tmp, "w", encoding="utf-8") as fh:
            # ASCII escapes keep names that are not UTF-8 (as surrogates).
            json.dump({"items": items}, fh)
        os.replace(tmp, self.index_path)

    def scan(self):
        roots = self.roots if self.roots is not None else \
            [self.home] + card_roots(self.user)
        found = walk(roots)
        with self.lock:
            old = dict(self.known)
        fresh, changed = {}, False
        for path, size, mtime in found:
            item = old.get(path)
            if not item or item["size"] != size or item["mtime"] != mtime:
                item = {"path": path, "kind": kind_of(path), "size": size, "mtime": mtime}
                if item["kind"] != "photo":
                    item.update(media_info(path, item["kind"]))
                changed = True
            fresh[path] = item
        if set(fresh) != set(old):
            changed = True
        with self.lock:
            self.known = fresh
        if changed:
            try:
                self.save()
            except OSError:
                pass
        return changed

    def forget(self, item):
        with self.lock:
            self.known.pop(item["path"], None)
        try:
            self.save()
        except OSError:
            pass

    # --- what the window shows ---------------------------------------------
    def items(self, kind="all"):
        with self.lock:
            items = list(self.known.values())
        if kind != "all":
            items = [i for i in items if i["kind"] == kind]
        items.sort(key=lambda i: (-i["mtime"], i["path"]))
        return items

    def counts(self):
        with self.lock:
            items = list(self.known.values())
        out = {k: 0 for k in KINDS}
        for i in items:
            out[i["kind"]] += 1
        out["all"] = len(items)
        return out

    @staticmethod
    def by_month(items):
        groups, labels = [], {}
        for i in items:
            label = month(i["mtime"])
            if label not in labels:
                labels[label] = []
                groups.append((label, labels[label]))
            labels[label].append(i)
        return groups

    def by_folder(self, items):
        groups, folders = [], {}
        for i in items:
            folder = os.path.dirname(i["path"])
            if folder not in folders:
                folders[folder] = []
                groups.append(folder)
            folders[folder].append(i)
        return [(self.folder_label(f), f, folders[f]) for f in groups]

    def folder_label(self, folder):
        if folder == self.home:
            return "Дом"
        if folder.startswith(self.home + os.sep):
            return os.path.relpath(folder, self.home)
        for base in ("/media/", "/run/media/%s/" % self.user):
            if folder.startswith(base):
                rest = folder[len(base):]
                card, _, tail = rest.partition(os.sep)
                return "Карта %s" % card + ("/" + tail if tail else "")
        return folder
