#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Install b8k-files (Файлы, and Галерея as b8k-files --gallery):
#   sh install.sh [ROOT] [PREFIX]
# ROOT empty or / for this system; PREFIX /usr/local unless given (a
# package passes /usr). It needs Python 3 with PyGObject (GTK 3) and
# b8k-compat (github.com/trudenboy/b8k-compat). The .desktop files make
# both programs appear in any desktop's launcher; the b8k tablet shell
# puts them on its home screen (X-B8K-Home).
set -eu
root=${1:-}
root=${root%/}
prefix=${2:-/usr/local}
here=$(cd "$(dirname "$0")" && pwd)
lib=$root$prefix/lib/b8k-files
share=$root$prefix/share
install -D -m 755 "$here/b8k-files" "$root$prefix/bin/b8k-files"
rm -rf "$lib"
for f in library media gallery; do
	install -D -m 644 "$here/$f.py" "$lib/$f.py"
done
for id in io.github.trudenboy.Files io.github.trudenboy.Gallery; do
	install -D -m 644 "$here/data/$id.desktop" "$share/applications/$id.desktop"
	install -D -m 644 "$here/data/$id.svg" "$share/icons/hicolor/scalable/apps/$id.svg"
	install -D -m 644 "$here/data/$id.metainfo.xml" "$share/metainfo/$id.metainfo.xml"
done
# The shell's old entries for these programs, from before the .desktop files.
rm -f "$root/usr/local/share/b8k/apps.d/files.conf" "$root/usr/local/share/b8k/apps.d/gallery.conf" \
	"$root/usr/local/share/b8k/files.svg" "$root/usr/local/share/b8k/gallery.svg"
