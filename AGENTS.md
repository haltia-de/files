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
- `haltia-documents`: Документы, the PDF viewer (`io.github.haltia_de.Documents`,
  package `haltia-documents`, an APKBUILD subpackage); `reading.py`: its
  PDF, pages and zoom over poppler-glib, without GTK, installed into
  `lib/haltia-documents`.
- `data/`: `.desktop` files, icons, metainfo, `haltia.portal`.
- `tests/`: `test_library.py`, `test_choosing.py`, `test_share.py` («Отправить»,
  without GTK or kit), `test_back.py` (app.back,
  and the portal started on a private bus with `dbus-run-session`),
  `test_documents.py` (reading.py on PDFs made with cairo).
- `install.sh`, `packaging/alpine/APKBUILD`, `.github/workflows/release.yml`.

## Run and check

From the checkout: `python3 haltia-files`, `python3 haltia-files --gallery`
(haltia-kit must be importable). Tests: `python3 tests/test_library.py` and
`python3 tests/test_choosing.py`; `python3 haltia-documents FILE.pdf` and
`python3 tests/test_documents.py` (poppler-glib, py3-cairo); the APKBUILD runs the same in `check()`.

## Install and package

`sh install.sh [ROOT] [PREFIX]` (PREFIX defaults to `/usr/local`; the
package passes `/usr`) installs the command, the modules into
`lib/haltia-files`, the data files and the D-Bus service for the portal.
Python never caches the script it is started by, so `haltia-files` and
`haltia-documents` go in twice: their code as the modules
`lib/haltia-files/haltia_files_main.py` and
`lib/haltia-documents/haltia_documents_main.py` (compiled with the rest by
the package build, haltia-de/ci), and `bin/NAME` as a stub that runs it with
`runpy.run_module(..., run_name="__main__", alter_sys=False)`, so `sys.argv`
(and the `python3 /usr/bin/NAME` command line) stays as it was. Code that
needs its own place uses `__file__`, which is the module in `lib/` (where
its sibling modules are), not `bin/NAME`. The scripts stay as they are in
the checkout, which the tests load by path.
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
