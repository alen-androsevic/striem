"""What a visitor reads: --help, script usage, licence and the links between docs."""

import re
import subprocess
import tomllib
from pathlib import Path
from xml.etree import ElementTree

import pytest

from striem import __version__
from striem.__main__ import parse_args

ROOT = Path(__file__).resolve().parents[1]
LICENSE_ID = "GPL-3.0-or-later"


def test_help_lists_the_keys_and_folders(capsys):
    with pytest.raises(SystemExit) as raised:
        parse_args(["striem", "--help"])
    assert raised.value.code == 0
    out = capsys.readouterr().out
    for phrase in ("save a frame", "save the last", "start or stop recording",
                   "~/Videos/Cameras", "~/Videos/Striem"):
        assert phrase in out


def test_version_names_the_build(capsys):
    with pytest.raises(SystemExit) as raised:
        parse_args(["striem", "--version"])
    assert raised.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_other_arguments_are_left_for_qt():
    assert parse_args(["striem", "-platform", "wayland"]) == ["-platform", "wayland"]


@pytest.mark.parametrize("script", ["install.sh", "build.sh", "scripts/fakecams.sh"])
def test_scripts_print_help_and_exit_cleanly(script):
    result = subprocess.run([ROOT / script, "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "usage:" in result.stdout


def test_license_is_declared_the_same_everywhere():
    assert "GNU GENERAL PUBLIC LICENSE" in (ROOT / "LICENSE").read_text()[:200]
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["license"] == LICENSE_ID
    metainfo = ElementTree.parse(ROOT / "flatpak" / "io.github.striem.Striem.metainfo.xml")
    assert metainfo.getroot().findtext("project_license") == LICENSE_ID


@pytest.mark.parametrize("doc", ["README.md", "CONTRIBUTING.md"])
def test_relative_links_resolve(doc):
    # Catches a moved screenshot or a renamed doc before GitHub shows a broken link.
    for target in re.findall(r"\]\((?!https?://|#)([^)\s]+)\)", (ROOT / doc).read_text()):
        assert (ROOT / target.split("#")[0]).exists(), target
