"""Offline build-script checks: python -m unittest -v test_build."""

from contextlib import ExitStack, redirect_stdout, redirect_stderr
import hashlib
import io
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

import build


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="test-openscad-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "model.scad").write_text("cube(1);", encoding="utf-8")
        self.targets = [
            {"fileIn": "model.scad", "fileOut": f"model{n}.stl", "N": n}
            for n in range(1, 5)
        ]

    def invoke(self, args, renderer):
        with patch.object(build, "ROOT", self.root), \
                patch.object(build, "TARGETS", self.targets), \
                patch.object(build, "find_openscad", return_value=Path("openscad")), \
                patch.object(build, "run", side_effect=renderer), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return build.main(args)

    @staticmethod
    def render(command, **kwargs):
        Path(command[2]).write_bytes(b"solid test\nendsolid test\n")
        return subprocess.CompletedProcess(command, 0, stdout="")

    def test_target_selection_and_defines(self):
        commands = []

        def renderer(command, **kwargs):
            commands.append(command)
            return self.render(command, **kwargs)

        self.targets[1].update(label='a "quoted" name', enabled=True, vector=[1, 2])
        self.assertEqual(self.invoke(["model2.stl", "model4.stl", "model2.stl"], renderer), 0)
        self.assertEqual(sorted(p.name for p in self.root.glob("*.stl")),
                         ["model2.stl", "model4.stl"])
        command = next(c for c in commands if "N=2" in c)
        self.assertIn('label="a \\"quoted\\" name"', command)
        self.assertIn("enabled=true", command)
        self.assertIn("vector=[1, 2]", command)
        self.assertEqual(command[-1], self.root / "model.scad")

    def test_freshness_includes_nested_python_and_all_scad(self):
        output = self.root / "model1.stl"
        output.write_bytes(b"old STL")
        timestamp = time.time_ns() - 10_000_000_000
        os.utime(output, ns=(timestamp, timestamp))
        (self.root / "tools").mkdir()
        helper = self.root / "tools/helper.py"
        helper.write_text("# dependency", encoding="utf-8")
        os.utime(helper, ns=(timestamp + 1, timestamp + 1))
        self.assertFalse(build.up_to_date(output, build.newest_source_mtime(self.root)))
        for source in self.root.rglob("*"):
            if source.suffix in (".py", ".scad"):
                os.utime(source, ns=(timestamp - 1, timestamp - 1))
        self.assertTrue(build.up_to_date(output, build.newest_source_mtime(self.root)))
        os.utime(helper, ns=(timestamp, timestamp))
        self.assertFalse(build.up_to_date(output, build.newest_source_mtime(self.root)))
        output.write_bytes(b"")
        self.assertFalse(build.up_to_date(output, 0))
        self.assertFalse(build.up_to_date(self.root / "missing.stl", 0))

    def test_current_outputs_skip_discovery_and_force_rebuilds(self):
        output = self.root / "model1.stl"
        output.write_bytes(b"existing")
        future = time.time_ns() + 10_000_000_000
        os.utime(output, ns=(future, future))
        with patch.object(build, "find_openscad") as discover:
            with patch.object(build, "ROOT", self.root), \
                    patch.object(build, "TARGETS", self.targets), redirect_stdout(io.StringIO()):
                self.assertEqual(build.main(["model1.stl"]), 0)
            discover.assert_not_called()
        self.assertEqual(self.invoke(["--force", "model1.stl"], self.render), 0)
        self.assertNotEqual(output.read_bytes(), b"existing")

    def test_parallel_limit_is_used(self):
        lock = threading.Lock()
        active = 0
        maximum = 0
        rendezvous = threading.Barrier(2)

        def renderer(command, **kwargs):
            nonlocal active, maximum
            with lock:
                active += 1
                maximum = max(maximum, active)
            rendezvous.wait(timeout=5)
            try:
                return self.render(command, **kwargs)
            finally:
                with lock:
                    active -= 1

        self.assertEqual(self.invoke(["--parallel", "2"], renderer), 0)
        self.assertEqual(maximum, 2)

    def test_failures_preserve_outputs_and_other_targets_complete(self):
        output = self.root / "model1.stl"
        output.write_bytes(b"keep me")

        def renderer(command, **kwargs):
            self.render(command, **kwargs)
            if "N=1" in command:
                return subprocess.CompletedProcess(command, 1, stdout="ERROR: bad model")
            return subprocess.CompletedProcess(command, 0, stdout="")

        self.assertEqual(self.invoke(["--force"], renderer), 1)
        self.assertEqual(output.read_bytes(), b"keep me")
        self.assertTrue((self.root / "model4.stl").is_file())
        self.assertEqual(list(self.root.glob(".*.stl")), [])

    def test_empty_or_error_output_is_failure_even_with_zero_exit(self):
        for diagnostics in ("", "ERROR: invalid geometry"):
            with self.subTest(diagnostics=diagnostics):
                def renderer(command, **kwargs):
                    if diagnostics:
                        self.render(command, **kwargs)
                    return subprocess.CompletedProcess(command, 0, stdout=diagnostics)
                self.assertEqual(self.invoke(["model1.stl"], renderer), 1)
                self.assertFalse((self.root / "model1.stl").exists())

    def test_unknown_targets_are_rejected(self):
        with self.assertRaisesRegex(build.BuildError, "Unknown target"):
            build.select_targets(["typo.stl"], self.targets, self.root)
        self.assertEqual(build.select_targets([str(self.root / "model2.stl")],
                                             self.targets, self.root), [self.targets[1]])

    def test_common_windows_nightly_location_without_path(self):
        executable = self.root / "OpenSCAD (Nightly)/openscad.com"
        executable.parent.mkdir()
        executable.touch()
        with patch.object(build.platform, "system", return_value="Windows"), \
                patch.object(build.shutil, "which", return_value=None), \
                patch.dict(os.environ, {"ProgramFiles": str(self.root)}), \
                patch.object(build, "windows_registry_candidates", return_value=iter(())), \
                patch.object(build, "usable", side_effect=lambda p: p == executable):
            self.assertEqual(build.find_openscad(), executable.resolve())

    def test_platform_download_keys(self):
        for system, machine, key in (
                ("Windows", "AMD64", "WIN64_ZIP"), ("Windows", "x86", "WIN32_ZIP"),
                ("Darwin", "arm64", "MAC"), ("Darwin", "x86_64", "MAC"),
                ("Linux", "x86_64", "LIN64"), ("Linux", "aarch64", "LIN_AARCH64")):
            self.assertEqual(build.download_platform_key(system, machine), key)
        with self.assertRaises(build.BuildError):
            build.download_platform_key("Linux", "riscv64")

    def test_discovery_preserves_symlink_launcher_name(self):
        # /snap/bin/openscad can point to /usr/bin/snap. Returning the resolved
        # path would lose the application name and launch snap itself.
        launcher = self.root / "openscad"
        with patch.object(build, "installed_candidates", return_value=iter([launcher])), \
                patch.object(build, "usable", return_value=True), \
                patch.object(Path, "resolve", side_effect=AssertionError("resolved launcher")):
            self.assertEqual(build.find_openscad(), launcher.absolute())

    def test_latest_download_compares_release_and_nightly_dates(self):
        metadata = [
            b"setSnapshotFileInfo('WIN64_ZIP_RELEASE', 'OpenSCAD 2021.01', '1 MB', "
            b"'https://files.openscad.org/old.zip');",
            b"setSnapshotFileInfo('WIN64_ZIP_SNAPSHOT', 'OpenSCAD-2026.10.29', '1 MB', "
            b"'https://files.openscad.org/snapshots/new.zip');",
        ]
        with patch.object(build, "download_platform_key", return_value="WIN64_ZIP"), \
                patch.object(build, "read_url", side_effect=lambda url: io.BytesIO(metadata.pop(0))):
            self.assertEqual(build.latest_download(), "https://files.openscad.org/snapshots/new.zip")

    def test_portable_setup_and_cleanup_for_each_platform(self):
        for system, suffix in (("Windows", ".zip"), ("Darwin", ".dmg"), ("Linux", ".AppImage")):
            with self.subTest(system=system):
                buffer = io.BytesIO()
                if system == "Windows":
                    with zipfile.ZipFile(buffer, "w") as package:
                        package.writestr("OpenSCAD/openscad.com", b"fake executable")
                payload = buffer.getvalue() or b"fake portable package"
                digest = hashlib.sha256(payload).hexdigest().encode()
                url = "https://files.openscad.org/OpenSCAD" + suffix

                def request(address):
                    return io.BytesIO(digest if address.endswith(".sha256") else payload)

                def setup(command, **kwargs):
                    if system == "Darwin":
                        executable = Path(command[-2]) / "OpenSCAD.app/Contents/MacOS/OpenSCAD"
                    else:
                        executable = Path(kwargs["cwd"]) / "squashfs-root/AppRun"
                    executable.parent.mkdir(parents=True)
                    executable.touch()
                    return subprocess.CompletedProcess(command, 0, stdout="")

                with patch.object(build.platform, "system", return_value=system), \
                        patch.object(build, "latest_download", return_value=url), \
                        patch.object(build, "read_url", side_effect=request), \
                        patch.object(build, "usable", return_value=True), \
                        patch.object(build, "run", side_effect=setup), \
                        patch.object(build.subprocess, "run") as detach, \
                        redirect_stdout(io.StringIO()):
                    with ExitStack() as stack:
                        executable = build.download_openscad(stack)
                        self.assertTrue(executable.is_file())
                    self.assertFalse(executable.exists())
                    if system == "Darwin":
                        detach.assert_called_once()

    def test_bad_download_checksum_is_rejected(self):
        with patch.object(build, "latest_download", return_value="https://files.openscad.org/test.zip"), \
                patch.object(build, "read_url", side_effect=lambda url: io.BytesIO(b"wrong")), \
                redirect_stdout(io.StringIO()), ExitStack() as stack:
            with self.assertRaisesRegex(build.BuildError, "SHA-256"):
                build.download_openscad(stack)


if __name__ == "__main__":
    unittest.main()
