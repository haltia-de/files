#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Keep the latest release notes and package version in agreement."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent.parent


class ReleaseTests(unittest.TestCase):
    def test_latest_release_matches_news(self):
        news = (HERE / "NEWS.md").read_text()
        heading = re.search(r"^## ([\d.]+) \(([^)]+)\)$", news, re.M)
        version, date = heading.groups()
        notes = news[heading.end():].split("\n## ", 1)[0]
        russian, english = notes.split("### English")
        expected = {
            "ru": re.findall(r"^- (.+)$", russian, re.M),
            "en": re.findall(r"^- (.+)$", english, re.M),
        }
        package = (HERE / "packaging/alpine/APKBUILD").read_text()
        self.assertIn(f"\npkgver={version}\n", package)
        self.assertIn("\npkgrel=0\n", package)
        metainfo = sorted((HERE / "data").glob("*.metainfo.xml"))
        self.assertTrue(metainfo)
        for path in metainfo:
            with self.subTest(path=path.name):
                release = ET.parse(path).find("./releases/release")
                self.assertEqual(release.attrib, {"version": version, "date": date})
                actual = {"ru": [], "en": []}
                for item in release.findall("./description/ul/li"):
                    language = item.get("{http://www.w3.org/XML/1998/namespace}lang", "en")
                    actual[language].append(item.text)
                self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
