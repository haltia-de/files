#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Install b8k-files (Файлы, and Галерея as b8k-files --gallery) into a root
# file system: sh install.sh [ROOT] (ROOT empty or / for this system). The
# tablet shell's build runs it for its image. It needs Python 3 with
# PyGObject (GTK 3); for media also python-mpv with libmpv (sound),
# ffmpeg (video pictures and lengths) and mutagen (sound tags and covers).
set -eu
root=${1:-}
root=${root%/}
here=$(cd "$(dirname "$0")" && pwd)
lib=$root/usr/local/lib/b8k-files
install -D -m 755 "$here/b8k-files" "$root/usr/local/bin/b8k-files"
rm -rf "$lib"
for f in library media gallery; do
	install -D -m 644 "$here/$f.py" "$lib/$f.py"
done
for f in files gallery; do
	install -D -m 644 "$here/$f.svg" "$root/usr/local/share/b8k/$f.svg"
	install -D -m 644 "$here/$f.conf" "$root/usr/local/share/b8k/apps.d/$f.conf"
done
