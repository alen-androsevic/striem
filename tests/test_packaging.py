import configparser
import os
from pathlib import Path

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
