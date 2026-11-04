#!/usr/bin/env python3
"""Build STL targets with Python 3.9+ and no third-party Python dependencies.

    python build.py                         # Build every stale/missing target
    python build.py -j 4 --force             # Rebuild all, four at a time
    python build.py strap2.stl joinerRegPoly4.stl

Edit TARGETS below to add models. Every key except fileIn/fileOut becomes an
OpenSCAD -D definition; strings are quoted automatically (use lists for vectors).
Paths are relative to this script, including when invoked from another directory.
If no usable installation is found, the newest official compatible release or
nightly is downloaded, checked against its SHA-256, and run from a temporary
directory that is removed after the build. No system installation is performed.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile


ROOT = Path(__file__).resolve().parent
TARGETS = [
    *({"fileIn": "strapN.scad", "N": n, "fileOut": f"strap{n}.stl"}
      for n in range(1, 8)),
    *({"fileIn": "WideStrapN.scad", "N": n, "fileOut": f"WideStrap{n}.stl"}
      for n in range(1, 8)),
    *({"fileIn": "joinerRegPoly.scad", "N": n,
       "fileOut": f"joinerRegPoly{n}.stl"} for n in range(2, 7)),
    *({"fileIn": "joiner2.scad", "N": n, "fileOut": f"joiner2{n}.stl"} for n in [1,4,9,16]),
    *({"fileIn": "joiner4.scad", "N": n, "fileOut": f"joiner4{n}.stl"} for n in [1,4,9,16]),
    *({"fileIn": "joinerHouse.scad", "N": n, "fileOut": f"joinerHouse{n}.stl"} for n in [1,4,9,16]),
    *({"fileIn": "limbMiddle.scad", "N": n, "fileOut": f"joinerMid{n}.stl"} for n in [2,3,4]),
    *({"fileIn": "CorsetHalf.scad", "N": n, "fileOut": f"corsetHalf{n}.stl"} for n in [1,2]),
    {"fileIn": "WideStrapJoiner.scad", "fileOut": "WideStrapJoiner.stl"},
    {"fileIn": "WideStrapJoiner.scad", "N", 1, "fileOut": "WideStrapJoinerScrewless.stl"},
    {"fileIn": "WideStrapJoinerUp.scad", "fileOut": "WideStrapRightAngleBase.stl"},
    {"fileIn": "upperChest.scad", "fileOut": "upperChest.stl"},
    *({"fileIn": "OvalCuff.scad", "X": n, "fileOut": f"cuff{n}.stl"} for n in [40, 43, 46, 49, 52, 55, 58, 61, 64, 67, 70, 75, 80, 85, 90, 95, 100, 110, 120, 130, 140, 150, 160, 170, 180, 190, 200]),
]

METADATA_URLS = (
    "https://openscad.org/inc/releases.js",
    "https://files.openscad.org/snapshots/.snapshots.js",
)


class BuildError(Exception):
    """A build or tool setup error suitable for displaying without a traceback."""


def run(command, **kwargs):
    """Capture console diagnostics, including those from Windows openscad.com."""
    env = os.environ.copy()
    if platform.system() == "Linux":
        env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return subprocess.run(
        [str(arg) for arg in command], stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
        env=env, **kwargs,
    )


def usable(executable):
    if not executable.is_file():
        return False
    try:
        result = run([executable, "--version"], timeout=20)
        return result.returncode == 0 and "openscad" in result.stdout.lower()
    except (OSError, subprocess.TimeoutExpired):
        return False


def windows_registry_candidates():
    """Include custom/per-user/nightly installs registered with Windows."""
    import winreg

    uninstall = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(hive, uninstall, 0, winreg.KEY_READ | view) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as app:
                                name = winreg.QueryValueEx(app, "DisplayName")[0]
                                if "openscad" not in name.lower():
                                    continue
                                for field in ("InstallLocation", "DisplayIcon"):
                                    try:
                                        value = winreg.QueryValueEx(app, field)[0]
                                    except OSError:
                                        continue
                                    value = os.path.expandvars(value)
                                    if field == "DisplayIcon":
                                        value = value.rsplit(",", 1)[0].strip('"')
                                        folder = Path(value).parent
                                    else:
                                        folder = Path(value.strip('"'))
                                    yield folder / "openscad.com"
                                    yield folder / "openscad.exe"
                        except OSError:
                            continue
            except OSError:
                continue


def installed_candidates():
    system = platform.system()
    names = ("openscad.com", "openscad.exe") if system == "Windows" else (
        "openscad", "openscad-nightly",
    )
    for name in names:
        found = shutil.which(name)
        if found:
            yield Path(found)

    home = Path.home()
    if system == "Windows":
        roots = [Path(os.environ[key]) for key in
                 ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")
                 if os.environ.get(key)]
        # Environment variables may be absent in stripped-down shells.
        roots += [Path("C:/Program Files"), Path("C:/Program Files (x86)")]
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        roots += [local, local / "Programs", home / "scoop/apps/openscad",
                  home / "scoop/apps/openscad-nightly"]
        for root in roots:
            for pattern in ("OpenSCAD*", "openscad*", "current"):
                for folder in sorted(root.glob(pattern), reverse=True):
                    for name in names:
                        yield folder / name
        yield from windows_registry_candidates()
    elif system == "Darwin":
        for root in (Path("/Applications"), home / "Applications",
                     Path("/opt/homebrew/Caskroom/openscad"),
                     Path("/opt/homebrew/Caskroom/openscad@snapshot"),
                     Path("/usr/local/Caskroom/openscad"),
                     Path("/usr/local/Caskroom/openscad@snapshot")):
            for pattern in ("OpenSCAD*.app", "*/OpenSCAD*.app"):
                for app in sorted(root.glob(pattern), reverse=True):
                    yield app / "Contents/MacOS/OpenSCAD"
        for root in ("/opt/homebrew/bin", "/usr/local/bin", "/opt/local/bin"):
            for name in names:
                yield Path(root) / name
    else:
        for root in ("/usr/bin", "/usr/local/bin", "/snap/bin",
                     str(home / ".local/bin"),
                     "/var/lib/flatpak/exports/bin",
                     str(home / ".local/share/flatpak/exports/bin")):
            for name in (*names, "org.openscad.OpenSCAD"):
                yield Path(root) / name
        for root in (Path("/opt"), home / "Applications", home / ".local/opt"):
            for pattern in ("OpenSCAD*.AppImage", "openscad*.AppImage",
                            "[Oo]pen[Ss][Cc][Aa][Dd]*/openscad",
                            "[Oo]pen[Ss][Cc][Aa][Dd]*/bin/openscad"):
                yield from sorted(root.glob(pattern), reverse=True)


def find_openscad(override=None):
    if override:
        candidate = Path(shutil.which(override) or override).expanduser()
        if candidate.is_dir() and candidate.suffix.lower() == ".app":
            candidate /= "Contents/MacOS/OpenSCAD"
        if usable(candidate):
            return candidate.absolute()
        raise BuildError(f"OpenSCAD is not runnable: {override}")
    seen = set()
    for candidate in installed_candidates():
        key = os.path.normcase(str(candidate.absolute()))
        if key not in seen:
            seen.add(key)
            if usable(candidate):
                # Snap/Flatpak launchers can be symlinks whose basename selects
                # the application; resolving them would invoke the wrong tool.
                return candidate.absolute()
    return None


def read_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "AshsStraps-build/1"})
    return urllib.request.urlopen(request, timeout=60)


def download_platform_key(system=None, machine=None):
    system = system or platform.system()
    machine = (machine or platform.machine()).lower()
    if system == "Windows":
        if machine in ("amd64", "x86_64", "x64"):
            return "WIN64_ZIP"
        if machine in ("i386", "i686", "x86"):
            return "WIN32_ZIP"
    elif system == "Darwin" and machine in ("arm64", "aarch64", "x86_64", "amd64"):
        return "MAC"
    elif system == "Linux":
        if machine in ("x86_64", "amd64"):
            return "LIN64"
        if machine in ("aarch64", "arm64"):
            return "LIN_AARCH64"
    raise BuildError(f"No official portable OpenSCAD download for {system}/{machine}. "
                     "Install OpenSCAD manually and supply --openscad PATH.")


def latest_download():
    """Read the same release/nightly metadata used by the official downloads page."""
    key = download_platform_key()
    choices = []
    errors = []
    pattern = re.compile(
        r"setSnapshotFileInfo\(\s*['\"]([^'\"]+)['\"]\s*,\s*"
        r"['\"]([^'\"]+)['\"]\s*,\s*['\"][^'\"]*['\"]\s*,\s*"
        r"['\"](https://[^'\"]+)['\"]\s*\)"
    )
    for metadata_url in METADATA_URLS:
        try:
            with read_url(metadata_url) as response:
                metadata = response.read().decode("utf-8")
        except (OSError, urllib.error.URLError) as exc:
            errors.append(f"{metadata_url}: {exc}")
            continue
        for entry_key, name, url in pattern.findall(metadata):
            if entry_key not in (key + "_RELEASE", key + "_SNAPSHOT"):
                continue
            if urllib.parse.urlparse(url).hostname != "files.openscad.org":
                continue
            # Old stable macOS builds are Intel-only; snapshots are universal.
            if (key == "MAC" and platform.machine().lower() in ("arm64", "aarch64")
                    and entry_key.endswith("_RELEASE")
                    and "universal" not in name.lower()):
                continue
            version = re.search(r"(\d{4})\.(\d{2})(?:\.(\d{2}))?", name)
            if version:
                date = tuple(int(part or 0) for part in version.groups())
                choices.append((date, url))
    if errors:
        # Do not silently claim an older release is the latest when nightly
        # metadata was unavailable (or vice versa).
        raise BuildError("Cannot determine the latest OpenSCAD download:\n" + "\n".join(errors))
    if not choices:
        raise BuildError(f"No portable {key} build in OpenSCAD's download metadata.")
    return max(choices)[1]


def download_openscad(stack):
    url = latest_download()
    folder = Path(stack.enter_context(tempfile.TemporaryDirectory(prefix="openscad-")))
    archive = folder / Path(urllib.parse.urlparse(url).path).name
    print(f"Downloading {url}", flush=True)
    digest = hashlib.sha256()
    with read_url(url) as response, archive.open("wb") as output:
        while chunk := response.read(1024 * 1024):
            output.write(chunk)
            digest.update(chunk)
    with read_url(url + ".sha256") as response:
        checksum = response.read().decode("utf-8")
    expected = re.search(r"\b[0-9a-fA-F]{64}\b", checksum)
    if not expected or digest.hexdigest() != expected.group().lower():
        raise BuildError(f"SHA-256 verification failed for {archive.name}")

    system = platform.system()
    if system == "Windows":
        with zipfile.ZipFile(archive) as package:
            package.extractall(folder / "unpacked")
        for name in ("openscad.com", "openscad.exe"):
            for executable in (folder / "unpacked").rglob(name):
                if usable(executable):
                    return executable
    elif system == "Darwin":
        mount = folder / "mount"
        mount.mkdir()
        result = run(["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint",
                      mount, archive])
        if result.returncode:
            raise BuildError(f"Could not mount OpenSCAD disk image:\n{result.stdout}")
        # Registered after the temporary directory so detach runs before cleanup.
        stack.callback(subprocess.run, ["hdiutil", "detach", str(mount)],
                       check=False, stdout=subprocess.DEVNULL)
        for executable in mount.glob("*.app/Contents/MacOS/OpenSCAD"):
            if usable(executable):
                return executable
    else:
        archive.chmod(0o755)
        # Extract once instead of requiring FUSE or re-extracting per worker.
        result = run([archive, "--appimage-extract"], cwd=folder)
        if result.returncode:
            raise BuildError(f"Could not extract OpenSCAD AppImage:\n{result.stdout}")
        executable = folder / "squashfs-root/AppRun"
        if usable(executable):
            return executable
    raise BuildError("Downloaded OpenSCAD could not be run on this machine.")


def newest_source_mtime(root):
    """Any project Python/SCAD change invalidates every target."""
    return max((path.stat().st_mtime_ns for path in root.rglob("*")
                if path.is_file() and path.suffix.lower() in (".py", ".scad")),
               default=0)


def up_to_date(output, source_mtime):
    try:
        stat = output.stat()
        return output.is_file() and stat.st_size > 0 and stat.st_mtime_ns > source_mtime
    except FileNotFoundError:
        return False


def target_key(name):
    return os.path.normcase(os.path.normpath(str(name)))


def select_targets(names, targets, root):
    by_name = {}
    for target in targets:
        for field in ("fileIn", "fileOut"):
            if field not in target:
                raise BuildError(f"Target is missing {field}: {target}")
        key = target_key(target["fileOut"])
        if key in by_name:
            raise BuildError(f"Duplicate output target: {target['fileOut']}")
        by_name[key] = target
    if not names:
        return list(by_name.values())
    selected = {}
    for name in names:
        path = Path(name)
        if path.is_absolute():
            try:
                path = path.relative_to(root)
            except ValueError:
                pass
        key = target_key(path)
        if key not in by_name:
            raise BuildError(f"Unknown target: {name}. Use --list to see available targets.")
        selected[key] = by_name[key]
    return list(selected.values())


def build_target(executable, target, root):
    output = root / target["fileOut"]
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, name = tempfile.mkstemp(prefix=f".{output.stem}-", suffix=output.suffix,
                                    dir=output.parent)
    os.close(handle)
    temporary = Path(name)
    try:
        command = [executable, "-o", temporary]
        for key, value in target.items():
            if key not in ("fileIn", "fileOut"):
                command += ["-D", f"{key}={json.dumps(value, allow_nan=False)}"]
        command.append(root / target["fileIn"])
        result = run(command, cwd=root)
        if (result.returncode or temporary.stat().st_size == 0
                or re.search(r"^\s*ERROR:", result.stdout, re.MULTILINE)):
            raise BuildError(f"{target['fileOut']}: OpenSCAD failed "
                             f"(exit {result.returncode})\n{result.stdout.strip()}")
        temporary.replace(output)
        return result.stdout.strip()
    finally:
        temporary.unlink(missing_ok=True)


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("parallel count must be at least 1")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help="output filenames (default: all)")
    parser.add_argument("-j", "--jobs", "--parallel", type=positive_int,
                        default=os.cpu_count() or 1, help="maximum parallel renders (default: CPU count)")
    parser.add_argument("-f", "--force", action="store_true", help="rebuild current outputs too")
    parser.add_argument("--openscad", default=os.environ.get("OPENSCAD"),
                        metavar="PATH", help="OpenSCAD executable (or set OPENSCAD)")
    parser.add_argument("--list", action="store_true", help="list configured targets and exit")
    args = parser.parse_args(argv)
    try:
        targets = select_targets(args.targets, TARGETS, ROOT)
        if args.list:
            for target in targets:
                defines = {k: v for k, v in target.items() if k not in ("fileIn", "fileOut")}
                print(f"{target['fileOut']} <- {target['fileIn']} {defines or ''}".rstrip())
            return 0
        source_mtime = newest_source_mtime(ROOT)
        pending = []
        for target in targets:
            if not args.force and up_to_date(ROOT / target["fileOut"], source_mtime):
                print(f"Up to date: {target['fileOut']}")
            else:
                pending.append(target)
        if not pending:
            print("All selected targets are up to date.")
            return 0
        for target in pending:
            if not (ROOT / target["fileIn"]).is_file():
                raise BuildError(f"Missing input: {target['fileIn']}")
        with ExitStack() as stack:
            executable = find_openscad(args.openscad)
            if executable is None:
                print("OpenSCAD not found; fetching the latest portable build.", flush=True)
                executable = download_openscad(stack)
            print(f"Using OpenSCAD: {executable}", flush=True)
            workers = min(args.jobs, len(pending))
            print(f"Building {len(pending)} target(s), up to {workers} in parallel.", flush=True)
            failures = 0
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(build_target, executable, target, ROOT): target
                           for target in pending}
                for future in as_completed(futures):
                    target = futures[future]
                    try:
                        diagnostics = future.result()
                        print(f"Built: {target['fileOut']}", flush=True)
                        if "WARNING:" in diagnostics:
                            print(diagnostics, flush=True)
                    except (BuildError, OSError, ValueError) as exc:
                        failures += 1
                        print(f"Failed: {exc}", file=sys.stderr, flush=True)
            print(f"{len(pending) - failures} built, {failures} failed.")
            return 1 if failures else 0
    except (BuildError, OSError, urllib.error.URLError, zipfile.BadZipFile) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
