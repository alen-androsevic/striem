import configparser
import os
import tomllib
from pathlib import Path
from xml.etree import ElementTree

import yaml

ROOT = Path(__file__).resolve().parents[1]
FLATPAK = ROOT / "flatpak"
APP_ID = "io.github.striem.Striem"


def manifest():
    return yaml.safe_load((FLATPAK / f"{APP_ID}.yml").read_text())


def all_modules(modules):
    for module in modules:
        if isinstance(module, dict):
            yield module
            yield from all_modules(module.get("modules", []))


def module(name):
    return next(m for m in all_modules(manifest()["modules"]) if m["name"] == name)


def test_manifest_identity_and_runtime():
    m = manifest()
    assert m["id"] == APP_ID
    assert m["command"] == "striem"
    assert (m["runtime"], m["runtime-version"], m["sdk"]) == ("org.kde.Platform", "6.11", "org.kde.Sdk")
    assert (m["base"], m["base-version"]) == ("io.qt.PySide.BaseApp", "6.11")
    assert "/app/cleanup-BaseApp.sh" in m["cleanup-commands"]


def test_manifest_permissions():
    assert set(manifest()["finish-args"]) == {
        "--share=ipc",
        "--share=network",
        "--socket=wayland",
        "--socket=fallback-x11",
        "--device=dri",
        "--socket=pulseaudio",
        "--filesystem=home:ro",
    }


def test_mpv_is_built_as_library_only():
    opts = module("libmpv")["config-opts"]
    assert "-Dlibmpv=true" in opts
    assert "-Dcplayer=false" in opts


def test_files_installed_by_app_module_exist():
    commands = " ".join(module("striem")["build-commands"])
    referenced = [tok for tok in commands.split() if tok.startswith(("flatpak/", "striem"))]
    assert referenced
    for rel in referenced:
        assert (ROOT / rel.rstrip("/")).exists(), rel


def test_desktop_entry():
    entry = configparser.ConfigParser(interpolation=None)
    entry.optionxform = str
    entry.read(FLATPAK / f"{APP_ID}.desktop")
    section = entry["Desktop Entry"]
    assert section["Exec"] == "striem"
    assert section["Icon"] == APP_ID
    assert section["Type"] == "Application"


def test_launcher_runs_package():
    assert "python3 -m striem" in (FLATPAK / "striem.sh").read_text()


def test_build_script_uses_manifest_and_is_executable():
    script = ROOT / "build.sh"
    assert f"flatpak/{APP_ID}.yml" in script.read_text()
    assert os.access(script, os.X_OK)


def test_build_script_bundle_mode_exports_a_single_file():
    script = (ROOT / "build.sh").read_text()
    assert "--bundle" in script
    # Bundle mode exports to a local repo instead of installing, then packs that
    # repo into one file that carries the runtime's origin with it.
    assert "--repo=repo" in script
    assert "build-bundle" in script
    assert "--runtime-repo=" in script
    assert "striem.flatpak" in script


def test_ci_workflow_bundles_the_same_manifest():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    step = workflow["jobs"]["bundle"]["steps"][-1]
    assert step["uses"].startswith("flatpak/flatpak-github-actions/flatpak-builder@")
    assert step["with"]["manifest-path"] == f"flatpak/{APP_ID}.yml"
    assert step["with"]["bundle"] == "striem.flatpak"


def test_bundle_builds_only_on_integration_branches():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    # YAML 1.1 reads a bare `on:` key as the boolean True, not the string "on".
    assert workflow[True]["push"]["branches"] == ["main", "next"]
    assert workflow["jobs"]["bundle"]["if"] == "github.event_name != 'pull_request'"
    # Tests are cheap and stay on every pull-request commit.
    assert "if" not in workflow["jobs"]["tests"]


def test_release_channels_are_wired_to_their_branches():
    workflow = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())
    jobs = workflow["jobs"]
    assert jobs["release"]["if"] == "startsWith(github.ref, 'refs/tags/v')"
    assert jobs["nightly"]["if"] == "github.ref == 'refs/heads/next'"

    stable = jobs["release"]["steps"][-1]["run"]
    nightly = jobs["nightly"]["steps"][-1]["run"]
    # The nightly is one rolling release: deleted and recreated each merge, and
    # never "Latest", so the Releases page keeps defaulting people to stable.
    assert "--cleanup-tag" in nightly
    assert "--prerelease" in nightly
    assert "striem-nightly.flatpak" in nightly
    assert "--prerelease" not in stable
    # Either release page can send you to the other channel.
    assert "releases/tag/nightly" in stable
    assert "releases/latest" in nightly


def test_metainfo_records_the_shipping_version():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    releases = ElementTree.parse(FLATPAK / f"{APP_ID}.metainfo.xml").getroot().find("releases")
    # Software centres read this file. It silently drifted through v0.1.1, so
    # the newest entry has to match what pyproject says we are shipping.
    assert releases[0].get("version") == version


def test_bundle_artifacts_are_ignored():
    ignored = (ROOT / ".gitignore").read_text().split()
    assert "repo/" in ignored
    assert "striem.flatpak" in ignored


def test_pycache_removed_before_copy():
    commands = module("striem")["build-commands"]
    clean_index = next(
        i for i, cmd in enumerate(commands) if "__pycache__" in cmd and "rm -rf" in cmd
    )
    copy_index = next(i for i, cmd in enumerate(commands) if cmd.startswith("cp -r striem"))
    assert clean_index < copy_index
