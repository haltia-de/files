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
  forget(item)    take a deleted file out (also out of a scan going on)

An item is a dict: path, kind, size, mtime, and for video and sound
duration (seconds or None), for sound title and artist when tagged. Hidden
folders (.cache, .local, ...) are not searched. Small pictures are
haltia-kit's freedesktop thumbnails (haltia_kit.photos).
"""
import json
import os
import tempfile
import threading

from haltia_kit.formats import month, nice_date, nice_duration, nice_size, plural  # noqa: F401
from haltia_kit.photos import kind_of, media_info

KINDS = ("photo", "video", "audio")
LIMIT = 30000  # files at most, so a huge card cannot eat the memory
DEPTH = 12
CHECKPOINT = 500  # files read in a scan between writes of the index


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
        self.forgotten = set()  # paths taken out since the scan began
        self.lock = threading.Lock()
        self.saving = threading.Lock()  # one writer of the index at a time

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

    def save(self, found=None):
        """Writes the index: what is known, and found (a scan's items so far)
        besides. One writer at a time, each through a file of its own."""
        os.makedirs(self.cache, mode=0o700, exist_ok=True)
        with self.saving:
            with self.lock:
                items = dict(self.known)
                if found:
                    items.update((p, i) for p, i in found.items() if p not in self.forgotten)
            fd, tmp = tempfile.mkstemp(prefix="index.", suffix=".new", dir=self.cache)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    # ASCII escapes keep names that are not UTF-8 (as surrogates).
                    json.dump({"items": list(items.values())}, fh)
                os.replace(tmp, self.index_path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise

    def save_quietly(self, found=None):
        try:
            self.save(found)
        except OSError:
            pass

    def scan(self):
        roots = self.roots if self.roots is not None else \
            [self.home] + card_roots(self.user)
        with self.lock:
            old = dict(self.known)
            self.forgotten = set()
        found = walk(roots)
        fresh, changed, read = {}, False, 0
        for path, size, mtime in found:
            item = old.get(path)
            if not item or item["size"] != size or item["mtime"] != mtime:
                item = {"path": path, "kind": kind_of(path), "size": size, "mtime": mtime}
                if item["kind"] != "photo":
                    item.update(media_info(path, item["kind"]))
                changed = True
                read += 1
                if read % CHECKPOINT == 0:  # a long scan cut short keeps its work
                    self.save_quietly(fresh)
            fresh[path] = item
        with self.lock:
            # Files deleted while the scan went on stay out.
            for path in self.forgotten:
                fresh.pop(path, None)
            self.known = fresh
        if set(fresh) != set(old):
            changed = True
        if changed:
            self.save_quietly()
        return changed

    def forget(self, item):
        """Takes a deleted file out; the index is written in a thread."""
        with self.lock:
            self.known.pop(item["path"], None)
            self.forgotten.add(item["path"])
        threading.Thread(target=self.save_quietly).start()

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
