#!/bin/sh
# SPDX-License-Identifier: GPL-2.0
# Install b8k-files into a root file system: sh install.sh [ROOT]
# (ROOT empty or / for this system). The tablet shell's build runs it for
# its image. It needs Python 3 with PyGObject (GTK 3) only.
set -eu
root=${1:-}
root=${root%/}
here=$(cd "$(dirname "$0")" && pwd)
install -D -m 755 "$here/b8k-files" "$root/usr/local/bin/b8k-files"
install -D -m 644 "$here/files.svg" "$root/usr/local/share/b8k/files.svg"
install -D -m 644 "$here/files.conf" "$root/usr/local/share/b8k/apps.d/files.conf"
