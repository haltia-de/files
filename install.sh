#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Install haltia-files (Файлы, and Галерея as haltia-files --gallery) and
# haltia-documents (Документы, the PDF viewer; it needs poppler-glib):
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
# stub NAME LIBDIR: Python never caches the script it is started by, so a
# command's code goes in as the module LIBDIR/NAME_main.py (- as _), compiled
# with the others by the package build, and bin/NAME is a stub that runs it
# with the same sys.argv (the shell matches `python3 /usr/bin/NAME`).
stub() {
	_module=$(printf %s "$1" | tr - _)_main
	install -D -m 644 "$here/$1" "$root$prefix/lib/$2/$_module.py"
	mkdir -p "$root$prefix/bin"
	cat >"$root$prefix/bin/$1" <<EOF
#!/usr/bin/python3
# The code is $prefix/lib/$2/$_module.py, run as a module so Python loads it compiled.
import runpy
import sys
sys.path.insert(0, "$prefix/lib/$2")
runpy.run_module("$_module", run_name="__main__", alter_sys=False)
EOF
	chmod 755 "$root$prefix/bin/$1"
}
rm -rf "$lib" "$root$prefix/lib/b8k-files"
stub haltia-files haltia-files
ln -sfn haltia-files "$root$prefix/bin/b8k-files"
for f in library media gallery choosing chooser portal; do
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
# Документы (haltia-documents), the PDF viewer: its own command and module
# folder, so the package splits it off; it opens from Файлы and Сообщения,
# not from the home screen (X-Haltia-Home=false).
rm -rf "$root$prefix/lib/haltia-documents"
stub haltia-documents haltia-documents
install -D -m 644 "$here/reading.py" "$root$prefix/lib/haltia-documents/reading.py"
id=io.github.haltia_de.Documents
install -D -m 644 "$here/data/$id.desktop" "$share/applications/$id.desktop"
install -D -m 644 "$here/data/$id.svg" "$share/icons/hicolor/scalable/apps/$id.svg"
install -D -m 644 "$here/data/$id.metainfo.xml" "$share/metainfo/$id.metainfo.xml"
# The file chooser for every program: an xdg-desktop-portal backend
# (portals/haltia.portal), started by D-Bus as haltia-files --portal.
install -D -m 644 "$here/data/haltia.portal" "$share/xdg-desktop-portal/portals/haltia.portal"
mkdir -p "$share/dbus-1/services"
printf '[D-BUS Service]\nName=org.freedesktop.impl.portal.desktop.haltia\nExec=%s/bin/haltia-files --portal\n' \
	"$prefix" >"$share/dbus-1/services/org.freedesktop.impl.portal.desktop.haltia.service"
# The shell's old entries for these programs, from before the .desktop files.
rm -f "$root/usr/local/share/b8k/apps.d/files.conf" "$root/usr/local/share/b8k/apps.d/gallery.conf" \
	"$root/usr/local/share/b8k/files.svg" "$root/usr/local/share/b8k/gallery.svg"
