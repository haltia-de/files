#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Install haltia-files (Файлы, and Галерея as haltia-files --gallery):
#   sh install.sh [ROOT] [PREFIX]
# ROOT empty or / for this system; PREFIX /usr/local unless given (a
# package passes /usr). It needs Python 3 with PyGObject (GTK 3) and
# haltia-kit (github.com/haltia-de/kit). The .desktop files make both
# programs appear in any desktop's launcher; the Haltia shell puts them on
# its home screen (X-Haltia-Home). The names before ADR 0004 (b8k-files,
# the ids io.github.trudenboy.Files and .Gallery, hidden) stay until 3.0.
set -eu
root=${1:-}
root=${root%/}
prefix=${2:-/usr/local}
here=$(cd "$(dirname "$0")" && pwd)
lib=$root$prefix/lib/haltia-files
share=$root$prefix/share
install -D -m 755 "$here/haltia-files" "$root$prefix/bin/haltia-files"
ln -sfn haltia-files "$root$prefix/bin/b8k-files"
rm -rf "$lib" "$root$prefix/lib/b8k-files"
for f in library media gallery; do
	install -D -m 644 "$here/$f.py" "$lib/$f.py"
done
for name in Files Gallery; do
	id=io.github.haltia_de.$name
	old=io.github.trudenboy.$name
	install -D -m 644 "$here/data/$id.desktop" "$share/applications/$id.desktop"
	install -D -m 644 "$here/data/$old.desktop" "$share/applications/$old.desktop"
	install -D -m 644 "$here/data/$id.svg" "$share/icons/hicolor/scalable/apps/$id.svg"
	install -D -m 644 "$here/data/$id.metainfo.xml" "$share/metainfo/$id.metainfo.xml"
	rm -f "$share/icons/hicolor/scalable/apps/$old.svg" "$share/metainfo/$old.metainfo.xml"
done
# The shell's old entries for these programs, from before the .desktop files.
rm -f "$root/usr/local/share/b8k/apps.d/files.conf" "$root/usr/local/share/b8k/apps.d/gallery.conf" \
	"$root/usr/local/share/b8k/files.svg" "$root/usr/local/share/b8k/gallery.svg"
