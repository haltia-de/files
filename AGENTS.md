# files

Файлы and Галерея of the [Haltia](https://github.com/haltia-de) desktop, and
the file chooser every program gets. One Python 3 program (PyGObject, GTK 3)
on top of [haltia-kit](https://github.com/haltia-de/kit). The project's
decisions and plans live in [haltia-de/haltia](https://github.com/haltia-de/haltia)
(`docs/adr/`, `docs/plans/`).

Program ids: `io.github.haltia_de.Files` and `io.github.haltia_de.Gallery`,
each with its own `.desktop`, icon and metainfo; the chooser window is
`io.github.haltia_de.FileChooser`. The old ids `io.github.trudenboy.*` and the
command `b8k-files` stay, hidden, until 3.0 (ADR 0004).

## Layout

- `haltia-files`: the entry point and Файлы; `--gallery` runs Галерея,
  `--portal` the file chooser.
- `gallery.py`: Галерея; `library.py`: its media library and cache.
- `media.py`: tiles, rows, viewer and sound bar shared by both.
- `portal.py`: the xdg-desktop-portal `FileChooser` backend over D-Bus;
  `chooser.py`: its window; `choosing.py`: its decisions, without GTK.
- `data/`: `.desktop` files, icons, metainfo, `haltia.portal`.
- `tests/`: `test_library.py`, `test_choosing.py`, `test_back.py` (app.back,
  and the portal started on a private bus with `dbus-run-session`).
- `install.sh`, `packaging/alpine/APKBUILD`, `.github/workflows/release.yml`.

## Run and check

From the checkout: `python3 haltia-files`, `python3 haltia-files --gallery`
(haltia-kit must be importable). Tests: `python3 tests/test_library.py` and
`python3 tests/test_choosing.py`; the APKBUILD runs the same in `check()`.

## Install and package

`sh install.sh [ROOT] [PREFIX]` (PREFIX defaults to `/usr/local`; the
package passes `/usr`) installs the command, the modules into
`lib/haltia-files`, the data files and the D-Bus service for the portal.
The Alpine package is `packaging/alpine/APKBUILD` (`haltia-files`, noarch).

## Release

SemVer. The tag `vX.Y.Z` equals `pkgver` in the APKBUILD and the newest
`<release>` in both metainfo files; the notes go into `NEWS.md` (Russian and
English). Pushing the tag runs `release.yml`, which builds the signed package
with `haltia-de/ci` and puts it into the GitHub release. A release needs the
user's approval: never tag or publish on your own.

## Conventions

Follow the shared rules in
[docs/conventions.md](https://github.com/haltia-de/haltia/blob/main/docs/conventions.md).
