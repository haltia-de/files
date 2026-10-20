# SPDX-License-Identifier: GPL-2.0
"""What the file chooser (chooser.py) decides, without GTK: which files a
program's filter lets through, which folder to start in, which name a
saved file gets, the places, recent files and dates in words.

A filter is the portal's: (name, [(0, glob) | (1, mime type)]).
"""
import fnmatch
import os
import time

from gi.repository import Gio, GLib

from haltia_kit.formats import MONTHS_OF, plural

HOME = os.path.expanduser("~")
RECENT_DAYS = 60
RECENT_MAX = 60
RECENT_DEPTH = 3

# The user's folders: XDG key, the Russian name (shown, and looked for when
# the key is not set), the English one.
FOLDERS = (("DOCUMENTS", "Документы", "Documents"),
           ("DOWNLOAD", "Загрузки", "Downloads"),
           ("PICTURES", "Изображения", "Pictures"),
           ("MUSIC", "Музыка", "Music"),
           ("VIDEOS", "Видео", "Videos"))
KEYS = {"DOCUMENTS": GLib.UserDirectory.DIRECTORY_DOCUMENTS,
        "DOWNLOAD": GLib.UserDirectory.DIRECTORY_DOWNLOAD,
        "PICTURES": GLib.UserDirectory.DIRECTORY_PICTURES,
        "MUSIC": GLib.UserDirectory.DIRECTORY_MUSIC,
        "VIDEOS": GLib.UserDirectory.DIRECTORY_VIDEOS}
DOCUMENT_MIMES = ("application/pdf", "application/rtf", "application/msword",
                  "application/vnd.oasis.opendocument.text",
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


def mime_of(name):
    ctype = Gio.content_type_guess(name, None)[0] or ""
    return Gio.content_type_get_mime_type(ctype) or ""


def user_dir(key, home=HOME):
    """A user folder that exists: by its XDG key, else by the Russian or
    the English name."""
    ru, en = next((r, e) for k, r, e in FOLDERS if k == key)
    path = GLib.get_user_special_dir(KEYS[key]) if home == HOME else None
    if path and os.path.normpath(path) != os.path.normpath(home) and os.path.isdir(path):
        return path
    for name in (ru, en):
        path = os.path.join(home, name)
        if os.path.isdir(path):
            return path
    return None


def places(everything=False, home=HOME, user=None):
    """[(label, path)] in the order shown. everything (the helper's switch)
    adds the home folder itself and the whole system."""
    out = [(ru, p) for p, ru in ((user_dir(k, home), ru) for k, ru, _e in FOLDERS) if p]
    user = user or os.environ.get("USER", "user")
    for base in ("/media", "/run/media/" + user, "/mnt"):
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            path = os.path.join(base, name)
            if os.path.ismount(path):
                out.append((card_label(name), path))
    if everything:
        out.insert(0, ("Дом", home))
        out.append(("Система", "/"))
    return out


def card_label(name):
    low = name.lower()
    if "sd" in low or "mmc" in low or "card" in low:
        return "Карта памяти"
    return "Флешка"


def matches(name, filt):
    """Whether a file's name passes a filter; None lets everything pass."""
    if not filt:
        return True
    rules = filt[1]
    if not rules:
        return True
    mime = None
    for kind, pattern in rules:
        if kind == 0:
            if fnmatch.fnmatchcase(name, pattern):
                return True
        else:
            if mime is None:
                mime = mime_of(name)
            if pattern == mime or pattern in ("*", "*/*") or (
                    pattern.endswith("/*") and mime.startswith(pattern[:-1])):
                return True
    return False


def filter_kind(filt):
    """"photo", "audio", "video" when every rule of a filter is that kind of
    file, else None."""
    if not filt or not filt[1]:
        return None
    kinds = set()
    for kind, pattern in filt[1]:
        if kind == 0:
            if pattern in ("*", "*.*"):
                return None
            mime = mime_of("x" + pattern.lstrip("*")) if pattern.startswith("*.") else ""
        else:
            mime = pattern
        top = mime.split("/")[0]
        kinds.add({"image": "photo", "audio": "audio", "video": "video"}.get(top))
    return kinds.pop() if len(kinds) == 1 and None not in kinds else None


def start_folder(current_folder=None, filt=None, last=None, home=HOME):
    """Where the chooser opens: the folder the program asked for, else the
    one its filter's kind of files live in, else the last one chosen in
    that program, else Загрузки (else home)."""
    for path in (current_folder,):
        if path and os.path.isdir(path):
            return path
    kind = filter_kind(filt)
    if kind:
        path = user_dir({"photo": "PICTURES", "audio": "MUSIC", "video": "VIDEOS"}[kind], home)
        if path:
            return path
    if last and os.path.isdir(last):
        return last
    return user_dir("DOWNLOAD", home) or home


def save_folder(name, current_folder=None, home=HOME):
    """Where a file is saved unless one chooses: the folder the program
    gave, else by kind (pictures, documents), else Загрузки."""
    if current_folder and os.path.isdir(current_folder):
        return current_folder
    mime = mime_of(name)
    key = None
    if mime.startswith("image/"):
        key = "PICTURES"
    elif mime.startswith("text/") or mime in DOCUMENT_MIMES:
        key = "DOCUMENTS"
    elif mime.startswith("audio/"):
        key = "MUSIC"
    elif mime.startswith("video/"):
        key = "VIDEOS"
    return (key and user_dir(key, home)) or user_dir("DOWNLOAD", home) or home


def new_name(now=None):
    """A name for a file the program gave none."""
    t = time.localtime(now if now is not None else time.time())
    return "Файл %d %s %02d-%02d" % (t.tm_mday, MONTHS_GENITIVE[t.tm_mon - 1], t.tm_hour, t.tm_min)


MONTHS_GENITIVE = ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
                   "сентября", "октября", "ноября", "декабря")


def free_name(folder, name):
    """name, or «name (2).ext», «name (3).ext»... when one is taken: a file
    is never written over."""
    clean = (name or "").replace("/", "").strip() or new_name()
    if clean in (".", ".."):
        clean = new_name()
    if not os.path.lexists(os.path.join(folder, clean)):
        return clean
    base, ext = split_ext(clean)
    n = 2
    while os.path.lexists(os.path.join(folder, "%s (%d)%s" % (base, n, ext))):
        n += 1
    return "%s (%d)%s" % (base, n, ext)


def split_ext(name):
    """("архив.tar", ".gz") is wrong for people: the known double ones stay
    whole; a leading dot is not an extension."""
    low = name.lower()
    for double in (".tar.gz", ".tar.xz", ".tar.bz2", ".tar.zst"):
        if low.endswith(double) and len(name) > len(double):
            return name[:-len(double)], name[-len(double):]
    base, ext = os.path.splitext(name)
    return (base, ext) if base else (name, "")


def when(mtime, now=None):
    """A file's date in words: «сегодня, 14:05», «вчера, 09:12», «12 окт»."""
    now = now if now is not None else time.time()
    t, n = time.localtime(mtime), time.localtime(now)
    day = time.mktime((n.tm_year, n.tm_mon, n.tm_mday, 0, 0, 0, 0, 0, -1))
    if mtime >= day:
        return "сегодня, %02d:%02d" % (t.tm_hour, t.tm_min)
    if mtime >= day - 86400:
        return "вчера, %02d:%02d" % (t.tm_hour, t.tm_min)
    text = "%d %s" % (t.tm_mday, MONTHS_OF[t.tm_mon - 1])
    return text if t.tm_year == n.tm_year else "%s %d" % (text, t.tm_year)


def objects(n):
    return "пусто" if n == 0 else plural(n, "объект", "объекта", "объектов")


def listing(folder, filt=None, folders_only=False, hidden=False):
    """[(is_dir, name, path, mtime)] of a folder: folders first by name,
    then the files that pass the filter, newest first."""
    dirs, files = [], []
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return None
    for e in entries:
        if not hidden and e.name.startswith("."):
            continue
        try:
            is_dir = e.is_dir()
            mtime = e.stat().st_mtime
        except OSError:
            continue
        if is_dir:
            dirs.append((True, e.name, e.path, mtime))
        elif not folders_only and matches(e.name, filt):
            files.append((False, e.name, e.path, mtime))
    dirs.sort(key=lambda x: x[1].casefold())
    files.sort(key=lambda x: -x[3])
    return dirs + files


def recent(roots, filt=None, now=None, days=RECENT_DAYS, limit=RECENT_MAX, depth=RECENT_DEPTH):
    """The newest files under the user's folders that pass the filter, from
    the last days, newest first: what one has just downloaded or saved."""
    since = (now if now is not None else time.time()) - days * 86400
    found, seen = [], set()
    stack = [(r, 0) for r in roots if r]
    while stack:
        folder, level = stack.pop()
        real = os.path.realpath(folder)
        if real in seen:
            continue
        seen.add(real)
        try:
            entries = list(os.scandir(folder))
        except OSError:
            continue
        for e in entries:
            if e.name.startswith("."):
                continue
            try:
                if e.is_dir(follow_symlinks=False):
                    if level + 1 < depth:
                        stack.append((e.path, level + 1))
                    continue
                if not e.is_file():
                    continue
                mtime = e.stat().st_mtime
            except OSError:
                continue
            if mtime >= since and matches(e.name, filt):
                found.append((False, e.name, e.path, mtime))
    found.sort(key=lambda x: -x[3])
    return found[:limit]


def media_share(entries):
    """The share of photos and videos among a listing's files: a folder of
    mostly pictures shows as tiles."""
    from haltia_kit.photos import kind_of
    files = [e for e in entries if not e[0]]
    if not files:
        return 0.0
    return sum(1 for e in files if kind_of(e[1]) in ("photo", "video")) / len(files)


def as_path(value):
    """A portal path option (ay, NUL-terminated) as text."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = bytes(value)
    if isinstance(value, bytes):
        value = value.rstrip(b"\0").decode("utf-8", "surrogateescape")
    return value or None
