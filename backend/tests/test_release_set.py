"""Release-set tests use generated source and wheel archives only."""
from __future__ import annotations

import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_release_set.py"
SOURCE_BUILDER = ROOT / "scripts" / "build_release_bundle.py"
WHEELHOUSE_BUILDER = ROOT / "scripts" / "build_offline_wheelhouse.py"
TARGET_PYTHON = "3.11"
TARGET_ABI = "cp311"
TARGET_PLATFORM = "manylinux_2_34_x86_64"


def load_release_set_module():
    spec = importlib.util.spec_from_file_location("release_set_test_subject", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseSetTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.git("init", "-q")

        self.wheelhouse = self.base / "wheelhouse"
        self.wheelhouse.mkdir()
        wheel = self.make_wheel()
        lock = (
            "# Synthetic exact runtime lock\n"
            f"synthetic-runtime==1.0 \\\n"
            f"    --hash=sha256:{self.sha256(wheel)}\n"
        ).encode()
        project = (
            "[project]\n"
            "name = 'synthetic-app'\n"
            "version = '1.0'\n"
            "dependencies = ['synthetic-runtime==1.0']\n"
        ).encode()
        self.sources = self.required_sources(project, lock)
        for name, data in self.sources.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for name in (".githooks/pre-push", "scripts/migrate_database.py",
                     "scripts/build_offline_wheelhouse.py", "scripts/build_release_set.py"):
            (self.repo / name).chmod(0o755)
        self.git("add", "-A")
        self.git("commit", "-qm", "synthetic fixture")
        self.commit = self.git("rev-parse", "HEAD").strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").strip()

        self.source_bundle = self.base / "source.tar.gz"
        result = subprocess.run(
            [sys.executable, str(SOURCE_BUILDER), "build", "--repo", str(self.repo),
             "--ref", self.commit, "--release-id", "synthetic-rc.1",
             "--output", str(self.source_bundle)],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.write_wheelhouse_manifest(wheel, project, lock)
        self.output = self.base / "release-set"
        self.python = self.base / "python3.11-test-wrapper"
        self.write_test_python(self.python, wrap_created_venv=True)

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Synthetic Test",
             "-c", "user.email=synthetic@example.invalid", *args],
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    @staticmethod
    def write_test_python(path: Path, *, wrap_created_venv: bool) -> None:
        probe = json.dumps({
            "implementation": "cp", "python_version": TARGET_PYTHON,
            "abi": TARGET_ABI, "platform": "linux", "machine": "x86_64",
            "glibc_version": "2.39",
        })
        child_template = (
            "#!{executable}\nimport json, os, pathlib, sys\n"
            "REAL = str(pathlib.Path(__file__).with_name('python-real'))\n"
            "if sys.argv[1:2] == ['-I']:\n    print({probe!r})\n"
            "else:\n    os.execv(REAL, [REAL, *sys.argv[1:]])\n"
        )
        source = (
            f"#!{sys.executable}\nimport json, os, pathlib, subprocess, sys\n"
            f"PROBE = {probe!r}\n"
            "if sys.argv[1:2] == ['-I']:\n"
            "    print(PROBE)\n"
            "elif sys.argv[1:3] == ['-m', 'venv']:\n"
            f"    subprocess.check_call([{str(Path(sys.executable))!r}, *sys.argv[1:]])\n"
        )
        if wrap_created_venv:
            source += (
                "    child = pathlib.Path(sys.argv[3]) / 'bin' / 'python'\n"
                "    real = child.with_name('python-real')\n"
                "    child.rename(real)\n"
                f"    child.write_text({child_template!r}.format("
                f"executable={str(Path(sys.executable))!r}, probe=PROBE))\n"
                "    child.chmod(0o755)\n"
            )
        source += (
            "else:\n"
            f"    os.execv({str(Path(sys.executable))!r}, "
            f"[{str(Path(sys.executable))!r}, *sys.argv[1:]])\n"
        )
        path.write_text(source)
        path.chmod(0o755)

    @staticmethod
    def sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def make_wheel(self) -> Path:
        path = self.wheelhouse / "synthetic_runtime-1.0-py3-none-any.whl"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "synthetic_runtime-1.0.dist-info/METADATA",
                "Metadata-Version: 2.1\nName: synthetic-runtime\nVersion: 1.0\n",
            )
            archive.writestr(
                "synthetic_runtime-1.0.dist-info/WHEEL",
                "Wheel-Version: 1.0\nGenerator: synthetic-test\n"
                "Root-Is-Purelib: true\nTag: py3-none-any\n",
            )
            archive.writestr("synthetic_runtime-1.0.dist-info/RECORD", "")
        return path

    @staticmethod
    def required_sources(project: bytes, lock: bytes) -> dict[str, bytes]:
        return {
            ".gitignore": b".env\n",
            ".githooks/pre-push": b"#!/bin/sh\nexit 0\n",
            "AGENTS.md": b"Synthetic constraints.\n",
            "README.md": b"Synthetic source.\n",
            "PROJECT_STATE.md": b"Synthetic state.\n",
            "backend/.env.example": b"DATABASE_URL=sqlite:///synthetic.db\n",
            "backend/pyproject.toml": project,
            "backend/requirements-release.lock": lock,
            "backend/app/main.py": (
                b"class Route:\n    path = '/health'\n\n"
                b"class App:\n    title = 'Synthetic AIOS'\n    routes = [Route()]\n\n"
                b"app = App()\n"
            ),
            "backend/app/db.py": b"# synthetic\n",
            "backend/app/migrations.py": b"# synthetic\n",
            "db/schema_phase0_draft.sql": b"SELECT 1;\n",
            "db/migrations/001_initial.sql": b"SELECT 1;\n",
            "docs/SPECIFICATION.md": b"Synthetic specification.\n",
            "docs/phase1/LAN_DEPLOYMENT.md": b"Synthetic deployment.\n",
            "docs/architecture/TENANT_OPERATIONS.md": b"Synthetic tenancy.\n",
            "deploy/systemd/fire-ai.service": b"[Service]\n",
            "deploy/nginx/fire-ai.conf": b"# synthetic\n",
            "deploy/windows/start-fire-ai.cmd": b"@echo synthetic\n",
            "frontend/index.html": b"<!doctype html><title>Synthetic</title>\n",
            "scripts/migrate_database.py": b"print('synthetic')\n",
            "scripts/build_offline_wheelhouse.py": b"print('synthetic')\n",
            "scripts/build_release_set.py": b"print('synthetic')\n",
        }

    def write_wheelhouse_manifest(self, wheel: Path, project: bytes, lock: bytes) -> None:
        manifest = {
            "schema_version": 1,
            "lock_sha256": hashlib.sha256(lock).hexdigest(),
            "project_sha256": hashlib.sha256(project).hexdigest(),
            "target": {
                "implementation": "cp",
                "python_version": TARGET_PYTHON,
                "abi": TARGET_ABI,
                "platform": TARGET_PLATFORM,
            },
            "files": {
                wheel.name: {
                    "distribution": "synthetic-runtime",
                    "version": "1.0",
                    "sha256": self.sha256(wheel),
                    "size": wheel.stat().st_size,
                }
            },
        }
        (self.wheelhouse / "WHEELHOUSE_MANIFEST.json").write_text(
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )

    def cli(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True, text=True,
        )

    def build(self, output: Path | None = None) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "build", "--source-bundle", self.source_bundle,
            "--wheelhouse", self.wheelhouse, "--output", output or self.output,
            "--implementation", "cp", "--python-version", TARGET_PYTHON,
            "--abi", TARGET_ABI, "--platform", TARGET_PLATFORM,
        )

    def verify(self) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "verify", self.output, "--expected-commit", self.commit,
        )

    def install(self, managed_root: Path) -> subprocess.CompletedProcess[str]:
        return self.install_with_python(managed_root, self.python)

    def install_with_python(
        self, managed_root: Path, python: Path,
    ) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "install", self.output, "--managed-root", managed_root,
            "--python", python, "--expected-commit", self.commit,
        )

    @staticmethod
    def result_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
        return json.loads(result.stdout.splitlines()[0])

    def test_build_binds_source_and_wheelhouse_deterministically(self) -> None:
        first = self.build()
        self.assertEqual(first.returncode, 0, first.stderr)
        second_output = self.base / "release-set-second"
        second = self.build(second_output)
        self.assertEqual(second.returncode, 0, second.stderr)

        first_manifest = (self.output / "RELEASE_SET_MANIFEST.json").read_bytes()
        self.assertEqual(first_manifest, (second_output / "RELEASE_SET_MANIFEST.json").read_bytes())
        manifest = json.loads(first_manifest)
        self.assertEqual(manifest["release_id"], "synthetic-rc.1")
        self.assertEqual(manifest["commit"], self.commit)
        self.assertEqual(manifest["tree"], self.tree)
        self.assertEqual(manifest["status"], "release-candidate")
        self.assertIs(manifest["production_ready"], False)
        self.assertEqual(manifest["source"]["sha256"], self.sha256(self.source_bundle))
        self.assertEqual(manifest["wheelhouse"]["wheel_count"], 1)
        self.assertEqual(manifest["wheelhouse"]["target"]["python_version"], TARGET_PYTHON)
        self.assertEqual(
            (self.output / manifest["source"]["path"]).read_bytes(),
            self.source_bundle.read_bytes(),
        )
        self.assertEqual(
            sorted(path.name for path in (self.output / manifest["wheelhouse"]["path"]).iterdir()),
            ["WHEELHOUSE_MANIFEST.json", "synthetic_runtime-1.0-py3-none-any.whl"],
        )

    def test_verify_rejects_substituted_source_without_traceback(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        clean = self.verify()
        self.assertEqual(clean.returncode, 0, clean.stderr)
        manifest = json.loads((self.output / "RELEASE_SET_MANIFEST.json").read_text())
        (self.output / manifest["source"]["path"]).write_bytes(b"substituted")

        rejected = self.verify()
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout)
        self.assertIn("source", rejected.stderr.lower())
        self.assertNotIn("Traceback", rejected.stderr)

    def test_verify_rejects_duplicate_manifest_key(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        path = self.output / "RELEASE_SET_MANIFEST.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                f'  "commit": "{self.commit}",\n',
                f'  "commit": "{self.commit}",\n  "commit": "{self.commit}",\n',
                1,
            ),
            encoding="utf-8",
        )

        rejected = self.verify()
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout)
        self.assertIn("duplicate", rejected.stderr.lower())
        self.assertNotIn("Traceback", rejected.stderr)

    def test_install_activates_verified_generation_and_rollback_restores_previous(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        managed_root = self.base / "managed"

        first = self.install(managed_root)
        self.assertEqual(first.returncode, 0, first.stderr)
        first_generation = self.result_json(first)["active_generation"]
        second = self.install(managed_root)
        self.assertEqual(second.returncode, 0, second.stderr)
        second_generation = self.result_json(second)["active_generation"]
        self.assertNotEqual(first_generation, second_generation)

        state_before = json.loads((managed_root / "state.json").read_text())
        self.assertEqual(state_before["active"]["generation"], second_generation)
        self.assertEqual(state_before["previous"]["generation"], first_generation)
        retained = managed_root / "generations" / first_generation / "release-set"
        self.assertTrue((retained / "RELEASE_SET_MANIFEST.json").is_file())
        self.assertTrue((retained / "wheelhouse" / "WHEELHOUSE_MANIFEST.json").is_file())

        rollback = self.cli("rollback", "--managed-root", managed_root)
        self.assertEqual(rollback.returncode, 0, rollback.stderr)
        result = self.result_json(rollback)
        self.assertEqual(result["active_generation"], first_generation)
        self.assertEqual(
            json.loads((managed_root / "state.json").read_text())["active"]["generation"],
            first_generation,
        )

    def test_rollback_rejects_tampered_previous_generation_without_switching(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        managed_root = self.base / "managed"
        first = self.install(managed_root)
        second = self.install(managed_root)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        active_before = (managed_root / "state.json").read_bytes()
        previous = json.loads((managed_root / "state.json").read_text())["previous"]
        tampered = managed_root / "generations" / previous["generation"] / "source" / "backend" / "app" / "main.py"
        tampered.write_text("# tampered\n", encoding="utf-8")

        rollback = self.cli("rollback", "--managed-root", managed_root)
        self.assertNotEqual(rollback.returncode, 0, rollback.stdout)
        self.assertIn("mismatch", rollback.stderr.lower())
        self.assertEqual((managed_root / "state.json").read_bytes(), active_before)
        self.assertNotIn("Traceback", rollback.stderr)

    def test_rollback_rejects_tampered_retained_wheel_without_switching(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        managed_root = self.base / "managed"
        self.assertEqual(self.install(managed_root).returncode, 0)
        self.assertEqual(self.install(managed_root).returncode, 0)
        state_path = managed_root / "state.json"
        state_before = state_path.read_bytes()
        previous = json.loads(state_path.read_text())["previous"]
        wheel = next(
            (managed_root / "generations" / previous["generation"] / "release-set" /
             "wheelhouse").glob("*.whl")
        )
        wheel.write_bytes(b"tampered wheel")

        rollback = self.cli("rollback", "--managed-root", managed_root)
        self.assertNotEqual(rollback.returncode, 0, rollback.stdout)
        self.assertIn("mismatch", rollback.stderr.lower())
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertNotIn("Traceback", rollback.stderr)

    def test_install_rejects_concurrent_operation_without_state_change(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        managed_root = self.base / "managed"
        managed_root.mkdir(mode=0o700)
        lock_path = managed_root / ".release-set-operation.lock"
        with lock_path.open("w+b") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            result = self.install(managed_root)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("operation is in progress", result.stderr.lower())
        self.assertFalse((managed_root / "state.json").exists())
        self.assertNotIn("Traceback", result.stderr)

    def test_install_rejects_symlink_managed_root(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        real = self.base / "real-managed"
        real.mkdir()
        managed_root = self.base / "managed-link"
        managed_root.symlink_to(real, target_is_directory=True)

        result = self.install(managed_root)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("managed root", result.stderr.lower())
        self.assertEqual(list(real.iterdir()), [])

    def test_failed_install_keeps_active_state_and_removes_staging(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        managed_root = self.base / "managed"
        first = self.install(managed_root)
        self.assertEqual(first.returncode, 0, first.stderr)
        state_before = (managed_root / "state.json").read_bytes()

        failed = self.install_with_python(managed_root, Path("/bin/false"))
        self.assertNotEqual(failed.returncode, 0, failed.stdout)
        self.assertEqual((managed_root / "state.json").read_bytes(), state_before)
        self.assertEqual(
            [path.name for path in (managed_root / "generations").iterdir()
             if path.name.startswith(".staging-")],
            [],
        )

    def test_install_rejects_interpreter_that_differs_from_bound_target(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        fake = self.base / "fake-python"
        fake.write_text("#!/bin/sh\nprintf '%s\\n' '{\"implementation\":\"cp\",\"python_version\":\"0.0\",\"abi\":\"cp00\",\"platform\":\"linux\",\"machine\":\"x86_64\",\"glibc_version\":\"2.34\"}'\n")
        fake.chmod(0o755)
        managed_root = self.base / "managed"

        result = self.install_with_python(managed_root, fake)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("target", result.stderr.lower())
        self.assertFalse((managed_root / "state.json").exists())

    def test_build_rejects_target_outside_bounded_linux_contract(self) -> None:
        result = self.cli(
            "build", "--source-bundle", self.source_bundle,
            "--wheelhouse", self.wheelhouse, "--output", self.output,
            "--implementation", "cp", "--python-version", TARGET_PYTHON,
            "--abi", TARGET_ABI, "--platform", "manylinux_2_34_aarch64",
        )
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("target", result.stderr.lower())
        self.assertFalse(self.output.exists())

    def test_install_rejects_wrong_architecture_and_old_glibc(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        for label, machine, glibc_version in (
            ("architecture", "aarch64", "2.40"),
            ("glibc", "x86_64", "2.33"),
        ):
            with self.subTest(label=label):
                fake = self.base / f"fake-python-{label}"
                probe = {
                    "implementation": "cp", "python_version": TARGET_PYTHON,
                    "abi": TARGET_ABI, "platform": "linux", "machine": machine,
                    "glibc_version": glibc_version,
                }
                fake.write_text(
                    "#!/bin/sh\nprintf '%s\\n' '" + json.dumps(probe) + "'\n"
                )
                fake.chmod(0o755)
                managed_root = self.base / f"managed-{label}"
                result = self.install_with_python(managed_root, fake)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(label, result.stderr.lower())
                self.assertFalse((managed_root / "state.json").exists())

    def test_install_rejects_launcher_that_creates_wrong_version_venv(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        launcher = self.base / "python-launcher-with-wrong-venv"
        self.write_test_python(launcher, wrap_created_venv=False)
        managed_root = self.base / "managed-wrong-venv"

        result = self.install_with_python(managed_root, launcher)

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("target", result.stderr.lower())
        self.assertFalse((managed_root / "state.json").exists())
        self.assertEqual(
            [path.name for path in (managed_root / "generations").iterdir()
             if path.name.startswith(".staging-")],
            [],
        )

    def test_state_commit_point_reports_post_rename_fsync_as_committed(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        module = load_release_set_module()
        managed_root = self.base / "managed"
        real_fsync = module.os.fsync

        def fail_root_directory_fsync(descriptor: int) -> None:
            target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            if target == managed_root:
                raise OSError("synthetic post-rename directory fsync failure")
            real_fsync(descriptor)

        with mock.patch.object(module.os, "fsync", side_effect=fail_root_directory_fsync):
            result = module.install_release_set(
                self.output, managed_root, self.python, self.commit
            )

        state = json.loads((managed_root / "state.json").read_text())
        self.assertEqual(state["active"]["generation"], result["active_generation"])
        self.assertIs(result["state_durability_confirmed"], False)

    def test_install_and_rollback_pre_rename_failure_keep_active_state(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        module = load_release_set_module()
        managed_root = self.base / "managed"
        first = module.install_release_set(
            self.output, managed_root, self.python, self.commit
        )
        state_path = managed_root / "state.json"
        state_before_install = state_path.read_bytes()
        real_replace = module.os.replace

        def fail_state_replace(source: object, destination: object) -> None:
            if Path(destination) == state_path:
                raise OSError("synthetic pre-rename failure")
            real_replace(source, destination)

        with mock.patch.object(module.os, "replace", side_effect=fail_state_replace):
            with self.assertRaises(OSError):
                module.install_release_set(
                    self.output, managed_root, self.python, self.commit
                )
        self.assertEqual(state_path.read_bytes(), state_before_install)

        second = module.install_release_set(
            self.output, managed_root, self.python, self.commit
        )
        self.assertNotEqual(first["active_generation"], second["active_generation"])
        state_before_rollback = state_path.read_bytes()
        with mock.patch.object(module.os, "replace", side_effect=fail_state_replace):
            with self.assertRaises(OSError):
                module.rollback_generation(managed_root)
        self.assertEqual(state_path.read_bytes(), state_before_rollback)

    def test_rollback_post_rename_fsync_is_reported_as_committed(self) -> None:
        self.assertEqual(self.build().returncode, 0)
        module = load_release_set_module()
        managed_root = self.base / "managed"
        first = module.install_release_set(
            self.output, managed_root, self.python, self.commit
        )
        second = module.install_release_set(
            self.output, managed_root, self.python, self.commit
        )
        real_fsync = module.os.fsync

        def fail_root_directory_fsync(descriptor: int) -> None:
            target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
            if target == managed_root:
                raise OSError("synthetic post-rename directory fsync failure")
            real_fsync(descriptor)

        with mock.patch.object(module.os, "fsync", side_effect=fail_root_directory_fsync):
            result = module.rollback_generation(managed_root)

        state = json.loads((managed_root / "state.json").read_text())
        self.assertEqual(state["active"]["generation"], first["active_generation"])
        self.assertEqual(state["previous"]["generation"], second["active_generation"])
        self.assertIs(result["state_durability_confirmed"], False)

    def test_verify_rejects_unknown_fields_boolean_sizes_and_extra_files(self) -> None:
        for mutation in ("unknown", "boolean-size", "extra-file"):
            with self.subTest(mutation=mutation):
                target = self.base / f"set-{mutation}"
                self.assertEqual(self.build(target).returncode, 0)
                manifest_path = target / "RELEASE_SET_MANIFEST.json"
                manifest = json.loads(manifest_path.read_text())
                if mutation == "unknown":
                    manifest["unexpected"] = "fail closed"
                    manifest_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                    )
                elif mutation == "boolean-size":
                    manifest["source"]["size"] = True
                    manifest_path.write_text(
                        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
                    )
                else:
                    (target / "extra.txt").write_text("not declared\n")
                rejected = self.cli("verify", target)
                self.assertNotEqual(rejected.returncode, 0, rejected.stdout)
                self.assertNotIn("Traceback", rejected.stderr)

    def test_build_rejects_symlinked_wheel_member(self) -> None:
        wheel = next(self.wheelhouse.glob("*.whl"))
        real = self.base / "real-wheel.whl"
        wheel.replace(real)
        wheel.symlink_to(real)

        rejected = self.build()
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout)
        self.assertIn("wheel", rejected.stderr.lower())
        self.assertFalse(self.output.exists())

    def test_release_workflow_exercises_unified_install_and_rollback(self) -> None:
        text = (ROOT / ".github" / "workflows" / "release-checks.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("build_release_bundle.py build", text)
        self.assertIn("build_release_set.py build", text)
        self.assertIn("build_release_set.py verify", text)
        self.assertGreaterEqual(text.count("build_release_set.py install"), 2)
        self.assertIn("build_release_set.py rollback", text)


if __name__ == "__main__":
    unittest.main()
