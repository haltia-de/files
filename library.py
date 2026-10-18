# SPDX-License-Identifier: GPL-2.0
"""The media library of Галерея (b8k-files --gallery): every photo, video
and sound file kept on the tablet, how it is grouped, and the small
pictures shown for it (Файлы shows them in its folders too).

Library(home, cache) is the one interface the window uses:

  load()          what was found last time (the index on disk), at once
  scan()          walk the home folder and the memory cards again; reuses
                  what is known of a file whose size and time are the same;
                  returns True when anything changed (blocking: a thread)
  items(kind)     the files of a kind ("all", "photo", "video", "audio"),
                  newest first
  by_month(items) [(label, items)] by the month the file was made
  by_folder(items) [(label, folder, items)] by folder, newest first
  thumb(item)     the path of its square small picture, made if missing
                  (blocking: a thread), or None when it has none
  forget(item)    take a deleted file out

An item is a dict: path, kind, size, mtime, and for video and sound
duration (seconds or None), for sound title and artist when tagged. Hidden
folders (.cache, .local, ...) are not searched. Video frames come from
ffmpeg, sound details and covers from mutagen; without them a file still
shows, with less to say.
"""
import hashlib
import json
import os
import subprocess
import threading
import time

PHOTO = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tif", "tiff", "svg"}
VIDEO = {"mp4", "m4v", "mkv", "webm", "avi", "mov", "3gp", "mpg", "mpeg", "ts", "wmv", "flv"}
AUDIO = {"mp3", "m4a", "aac", "ogg", "oga", "opus", "flac", "wav", "wma", "amr"}
KINDS = ("photo", "video", "audio")
LIMIT = 30000  # files at most, so a huge card cannot eat the memory
DEPTH = 12
THUMB = 256  # px, square
# Pictures come from anywhere (chats, cards): one too large to decode in the
# tablet's memory is left alone.
MAX_PIXELS = 60 * 1000 * 1000
MAX_COVER = 8 * 1024 * 1024
# ffmpeg and ffprobe read files that came from anywhere (a chat, a card):
# only the file itself, no network and no playlists reaching other files.
SAFE = ["-protocol_whitelist", "file", "-format_whitelist",
        "mov,mp4,m4a,3gp,3g2,mj2,matroska,webm,avi,mpeg,mpegts,asf,flv,mp3,ogg,flac,wav,aac,amr"]
MONTHS = ("Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август",
          "Сентябрь", "Октябрь", "Ноябрь", "Декабрь")
MONTHS_OF = ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя",
             "дек")


def kind_of(name):
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext in PHOTO:
        return "photo"
    if ext in VIDEO:
        return "video"
    if ext in AUDIO:
        return "audio"
    return None


def nice_size(n):
    for unit in ("Б", "КБ", "МБ", "ГБ"):
        if n < 1024 or unit == "ГБ":
            return ("%d %s" if unit == "Б" else "%.1f %s") % (n, unit)
        n /= 1024.0
    return ""


def nice_duration(sec):
    if sec is None:
        return ""
    sec = int(round(sec))
    h, rest = divmod(sec, 3600)
    m, s = divmod(rest, 60)
    return "%d:%02d:%02d" % (h, m, s) if h else "%d:%02d" % (m, s)


def nice_date(mtime, now=None):
    t = time.localtime(mtime)
    n = time.localtime(now if now is not None else time.time())
    day = "%d %s" % (t.tm_mday, MONTHS_OF[t.tm_mon - 1])
    return day if t.tm_year == n.tm_year else "%s %d" % (day, t.tm_year)


def files_word(n):
    tail = n % 100
    if 11 <= tail <= 14 or n % 10 in (0, 5, 6, 7, 8, 9):
        return "%d файлов" % n
    return "%d файл" % n if n % 10 == 1 else "%d файла" % n


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


def probe(path, kind):
    """Duration, and for sound title and artist, as far as known."""
    info = {"duration": None}
    if kind == "audio":
        try:
            import mutagen

            f = mutagen.File(path, easy=True)
            if f is not None:
                if getattr(f, "info", None) and getattr(f.info, "length", None):
                    info["duration"] = float(f.info.length)
                tags = f.tags or {}
                for key in ("title", "artist"):
                    v = tags.get(key) if hasattr(tags, "get") else None
                    if v:
                        info[key] = str(v[0] if isinstance(v, list) else v)
        except Exception:
            pass
    if kind in ("video", "audio") and info["duration"] is None:
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error"] + SAFE +
                ["-show_entries", "format=duration", "-of", "default=nw=1:nk=1",
                 "file:" + path], capture_output=True, text=True, timeout=20)
            info["duration"] = float(out.stdout.strip())
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return info


def cover_bytes(path):
    """The embedded cover of a sound file, as image bytes, or None."""
    try:
        import mutagen

        f = mutagen.File(path)
    except Exception:
        return None
    if f is None:
        return None
    pictures = getattr(f, "pictures", None)
    if pictures:
        return pictures[0].data
    tags = getattr(f, "tags", None) or {}
    try:
        for key in list(tags.keys()):
            if key.startswith("APIC"):
                return tags[key].data
            if key == "covr" and tags[key]:
                return bytes(tags[key][0])
            if key == "metadata_block_picture":
                import base64

                from mutagen.flac import Picture

                return Picture(base64.b64decode(tags[key][0])).data
    except Exception:
        return None
    return None


def square(pix, size=THUMB):
    """The middle square of a pixbuf, scaled to size."""
    from gi.repository import GdkPixbuf

    w, h = pix.get_width(), pix.get_height()
    side = min(w, h)
    part = pix.new_subpixbuf((w - side) // 2, (h - side) // 2, side, side)
    return part.scale_simple(size, size, GdkPixbuf.InterpType.BILINEAR)


def pixbuf_of(path, size):
    """A picture file at about size px on its short side, upright."""
    from gi.repository import GdkPixbuf

    _fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(path)  # -1 when it cannot tell
    if w <= 0 or h <= 0 or w * h > MAX_PIXELS:
        raise ValueError("picture too large or of unknown size: %s" % path)
    k = size / float(min(w, h))
    pix = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, max(1, int(w * k + 0.5)),
                                                  max(1, int(h * k + 0.5)), True)
    return pix.apply_embedded_orientation() or pix


class Library:
    def __init__(self, home, cache, user=None, roots=None):
        self.home = home
        self.cache = cache
        self.user = user or os.environ.get("USER", "")
        self.roots = roots
        self.index_path = os.path.join(cache, "index.json")
        self.thumbs = os.path.join(cache, "thumbs")
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
            json.dump({"items": items}, fh, ensure_ascii=False)
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
                    item.update(probe(path, item["kind"]))
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

    def prune(self, keep=4000):
        """Small pictures beyond keep go, the longest unused first."""
        try:
            names = [e for e in os.scandir(self.thumbs) if e.is_file()]
        except OSError:
            return
        if len(names) <= keep:
            return
        names.sort(key=lambda e: e.stat().st_atime)
        for e in names[:len(names) - keep]:
            try:
                os.unlink(e.path)
            except OSError:
                pass

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
            t = time.localtime(i["mtime"])
            label = "%s %d" % (MONTHS[t.tm_mon - 1], t.tm_year)
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

    # --- small pictures ----------------------------------------------------
    def thumb_path(self, item):
        key = "%s|%d|%f" % (item["path"], item["size"], item["mtime"])
        return os.path.join(self.thumbs, hashlib.sha1(key.encode()).hexdigest() + ".jpg")

    def thumb(self, item):
        out = self.thumb_path(item)
        if os.path.exists(out):
            return out
        os.makedirs(self.thumbs, mode=0o700, exist_ok=True)
        if os.path.exists(out + ".none"):
            return None
        try:
            made = self._make(item, out)
        except Exception:
            made = False
        if not made:
            try:
                open(out + ".none", "w").close()  # tried: not again for this file
            except OSError:
                pass
            return None
        return out

    def _make(self, item, out):
        from gi.repository import GdkPixbuf, GLib

        path, kind = item["path"], item["kind"]
        tmp = out + ".tmp"
        if kind == "photo":
            pix = pixbuf_of(path, THUMB)
        elif kind == "video":
            frame = out + ".frame.jpg"
            dur = item.get("duration")
            # A frame a little in (the first is often black), else the first.
            pix = None
            try:
                for at in (min(3.0, dur / 3.0) if dur else 1.0, 0.0):
                    subprocess.run(
                        ["ffmpeg", "-v", "error", "-y"] + SAFE + ["-ss", "%.2f" % at, "-i",
                                                                  "file:" + path,
                         "-frames:v", "1", "-vf",
                         "scale=%d:%d:force_original_aspect_ratio=increase" % (THUMB, THUMB),
                         frame], capture_output=True, timeout=60)
                    if os.path.exists(frame) and os.path.getsize(frame) > 0:
                        pix = GdkPixbuf.Pixbuf.new_from_file(frame)
                        break
            except (OSError, subprocess.SubprocessError, GLib.Error):
                return False
            finally:
                try:
                    os.unlink(frame)
                except OSError:
                    pass
        else:
            data = cover_bytes(path)
            if not data or len(data) > MAX_COVER:
                return False
            loader = GdkPixbuf.PixbufLoader()

            too_big = []

            def prepared(ld, w, h):
                # An exception here would only be printed, the decoding going on:
                # a refusal is kept and the picture shrunk to a pixel instead.
                if w * h > MAX_PIXELS:
                    too_big.append(True)
                    ld.set_size(1, 1)
                    return
                k = min(1.0, THUMB / float(max(w, h, 1)))
                ld.set_size(max(1, int(w * k)), max(1, int(h * k)))  # scaled as it decodes

            loader.connect("size-prepared", prepared)
            loader.write(data)
            loader.close()
            if too_big:
                return False
            pix = loader.get_pixbuf()
        if pix is None:
            return False
        square(pix).savev(tmp, "jpeg", ["quality"], ["85"])
        os.replace(tmp, out)
        return True
