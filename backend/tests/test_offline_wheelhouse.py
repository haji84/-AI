"""Offline wheelhouse tests use generated package archives only."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_offline_wheelhouse.py"


class OfflineWheelhouseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.wheelhouse = self.base / "wheelhouse"
        self.wheelhouse.mkdir()
        self.lock = self.base / "requirements.lock"
        self.project = self.base / "pyproject.toml"
        self.project.write_text(
            "[project]\nname = 'synthetic'\ndependencies = "
            "['alpha>=1,<2']\n",
            encoding="utf-8",
        )

    def make_wheel(
        self,
        distribution: str,
        version: str,
        *,
        tag: str = "py3-none-any",
        requires_dist: tuple[str, ...] = (),
        requires_python: str | None = None,
        provides_extra: tuple[str, ...] = (),
    ) -> Path:
        filename = f"{distribution.replace('-', '_')}-{version}-{tag}.whl"
        path = self.wheelhouse / filename
        dist_info = f"{distribution.replace('-', '_')}-{version}.dist-info"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                f"{dist_info}/METADATA",
                f"Metadata-Version: 2.1\nName: {distribution}\nVersion: {version}\n"
                + (f"Requires-Python: {requires_python}\n" if requires_python else "")
                + "".join(f"Provides-Extra: {item}\n" for item in provides_extra)
                + "".join(f"Requires-Dist: {item}\n" for item in requires_dist),
            )
            archive.writestr(
                f"{dist_info}/WHEEL",
                "Wheel-Version: 1.0\nGenerator: synthetic-test\n"
                f"Root-Is-Purelib: true\nTag: {tag}\n",
            )
            archive.writestr(f"{dist_info}/RECORD", "")
        return path

    def write_lock(self, wheels: list[tuple[str, str, Path]]) -> None:
        lines = ["# Synthetic exact runtime lock"]
        for distribution, version, path in wheels:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            lines.extend((f"{distribution}=={version} \\", f"    --hash=sha256:{digest}"))
        self.lock.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def write_manifest(self, wheels: list[Path], *, lock_digest: str | None = None) -> None:
        files = {}
        for path in wheels:
            distribution, version = path.name.split("-")[:2]
            files[path.name] = {
                "distribution": distribution.replace("_", "-"),
                "version": version,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size": path.stat().st_size,
            }
        manifest = {
            "schema_version": 1,
            "lock_sha256": lock_digest or hashlib.sha256(self.lock.read_bytes()).hexdigest(),
            "project_sha256": hashlib.sha256(self.project.read_bytes()).hexdigest(),
            "target": {
                "implementation": "cp",
                "python_version": "3.11",
                "abi": "cp311",
                "platform": "manylinux_2_28_x86_64",
            },
            "files": files,
        }
        (self.wheelhouse / "WHEELHOUSE_MANIFEST.json").write_text(
            json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
        )

    def cli(self, *args: object) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)],
            capture_output=True,
            text=True,
        )

    def verify(self) -> subprocess.CompletedProcess[str]:
        return self.cli(
            "verify",
            "--lock",
            self.lock,
            "--wheelhouse",
            self.wheelhouse,
            "--project",
            self.project,
            "--implementation",
            "cp",
            "--python-version",
            "3.11",
            "--abi",
            "cp311",
            "--platform",
            "manylinux_2_28_x86_64",
        )

    def assert_invalid(self, expected: str) -> None:
        result = self.verify()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn(expected.lower(), result.stderr.lower())
        self.assertNotIn("traceback", result.stderr.lower())

    def test_verify_accepts_exact_hash_bound_wheel_set(self):
        alpha = self.make_wheel("alpha", "1.0")
        beta = self.make_wheel("beta-pkg", "2.0")
        self.write_lock([("alpha", "1.0", alpha), ("beta-pkg", "2.0", beta)])
        self.project.write_text(
            "[project]\nname = 'synthetic'\ndependencies = "
            "['alpha>=1,<2', 'beta-pkg==2.0']\n",
            encoding="utf-8",
        )
        self.write_manifest([alpha, beta])

        result = self.verify()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("2 wheels", result.stdout)
        self.assertIn("offline", result.stdout.lower())

    def test_verify_rejects_tamper_extra_missing_sdist_and_lock_change(self):
        wheel = self.make_wheel("alpha", "1.0")
        self.write_lock([("alpha", "1.0", wheel)])
        self.write_manifest([wheel])
        pristine = wheel.read_bytes()

        wheel.write_bytes(pristine + b"tamper")
        self.assert_invalid("hash")
        wheel.write_bytes(pristine)

        extra = self.wheelhouse / "extra-1.0-py3-none-any.whl"
        extra.write_bytes(pristine)
        self.assert_invalid("extra")
        extra.unlink()

        wheel.unlink()
        self.assert_invalid("missing")
        wheel.write_bytes(pristine)

        sdist = self.wheelhouse / "alpha-1.0.tar.gz"
        sdist.write_bytes(b"not allowed")
        self.assert_invalid("sdist")
        sdist.unlink()

        self.lock.write_text(self.lock.read_text() + "# changed\n", encoding="utf-8")
        self.assert_invalid("lock")

    def test_verify_rejects_unlocked_hash_duplicate_distribution_and_wrong_target(self):
        alpha = self.make_wheel("alpha", "1.0")
        other = self.make_wheel("alpha", "2.0")
        self.write_lock([("alpha", "1.0", alpha)])
        self.write_manifest([alpha, other])
        self.assert_invalid("distribution")
        other.unlink()

        replacement = self.make_wheel("alpha", "1.0")
        with zipfile.ZipFile(replacement, "a") as archive:
            archive.writestr("payload.txt", "changed")
        self.write_manifest([replacement])
        self.assert_invalid("lock hash")

        self.write_lock([("alpha", "1.0", replacement)])
        self.write_manifest([replacement])
        result = self.cli(
            "verify", "--project", self.project, "--lock", self.lock,
            "--wheelhouse", self.wheelhouse,
            "--implementation", "cp", "--python-version", "3.12",
            "--abi", "cp312", "--platform", "manylinux_2_28_x86_64",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target", result.stderr.lower())

    def test_verify_rejects_non_exact_or_unhashed_lock_entries(self):
        wheel = self.make_wheel("alpha", "1.0")
        for requirement in ("alpha>=1.0", "alpha==1.0", "alpha==1.0; python_version >= '3.11'"):
            with self.subTest(requirement=requirement):
                self.lock.write_text(requirement + "\n", encoding="utf-8")
                self.write_manifest([wheel])
                self.assert_invalid("lock")

    def test_verify_binds_lock_to_current_project_requirements(self):
        alpha = self.make_wheel("alpha", "1.0")
        beta = self.make_wheel("beta-pkg", "2.0")
        self.write_lock([("alpha", "1.0", alpha), ("beta-pkg", "2.0", beta)])
        self.write_manifest([alpha, beta])

        self.project.write_text(
            "[project]\nname = 'synthetic'\ndependencies = "
            "['alpha>=2,<3']\n",
            encoding="utf-8",
        )

        self.assert_invalid("project")

    def test_verify_rejects_wheel_incompatible_with_declared_target(self):
        alpha = self.make_wheel("alpha", "1.0", tag="cp312-cp312-win_amd64")
        self.write_lock([("alpha", "1.0", alpha)])
        self.write_manifest([alpha])

        self.assert_invalid("compatible")

        alpha.unlink()
        native_any = self.make_wheel("alpha", "1.0", tag="cp311-cp311-any")
        self.write_lock([("alpha", "1.0", native_any)])
        self.write_manifest([native_any])
        self.assert_invalid("compatible")

        native_any.unlink()
        pre_abi3 = self.make_wheel(
            "alpha", "1.0", tag="cp31-abi3-manylinux_2_28_x86_64"
        )
        self.write_lock([("alpha", "1.0", pre_abi3)])
        self.write_manifest([pre_abi3])
        self.assert_invalid("compatible")

    def test_verify_rejects_target_outside_project_requires_python(self):
        alpha = self.make_wheel("alpha", "1.0")
        self.write_lock([("alpha", "1.0", alpha)])
        self.project.write_text(
            "[project]\nname = 'synthetic'\nrequires-python = '>=3.12'\n"
            "dependencies = ['alpha>=1,<2']\n",
            encoding="utf-8",
        )
        self.write_manifest([alpha])

        self.assert_invalid("requires-python")

    def test_verify_rejects_missing_selected_extra_dependency(self):
        alpha = self.make_wheel(
            "alpha",
            "1.0",
            requires_dist=("beta>=2; extra == 'feature'",),
            provides_extra=("feature",),
        )
        self.write_lock([("alpha", "1.0", alpha)])
        self.project.write_text(
            "[project]\nname = 'synthetic'\n"
            "dependencies = ['alpha[feature]>=1,<2']\n",
            encoding="utf-8",
        )
        self.write_manifest([alpha])

        self.assert_invalid("dependency missing from lock")

    def test_verify_rejects_selected_extra_not_declared_by_wheel(self):
        alpha = self.make_wheel("alpha", "1.0")
        self.write_lock([("alpha", "1.0", alpha)])
        self.project.write_text(
            "[project]\nname = 'synthetic'\n"
            "dependencies = ['alpha[feature]>=1,<2']\n",
            encoding="utf-8",
        )
        self.write_manifest([alpha])

        self.assert_invalid("selected extras not provided")

    def test_verify_fails_closed_for_active_pep508_marker_forms(self):
        cases = (
            ("alpha[feature_one]>=1,<2", "beta>=2; extra == 'feature_one'"),
            ("alpha>=1,<2", "beta>=2; '3.9' < python_version"),
            ("alpha>=1,<2", "beta>=2; python_version === '3.11'"),
        )
        for project_requirement, dependency_requirement in cases:
            with self.subTest(marker=dependency_requirement):
                for path in self.wheelhouse.glob("*.whl"):
                    path.unlink()
                alpha = self.make_wheel(
                    "alpha",
                    "1.0",
                    requires_dist=(dependency_requirement,),
                    provides_extra=("feature_one",),
                )
                self.write_lock([("alpha", "1.0", alpha)])
                self.project.write_text(
                    "[project]\nname = 'synthetic'\ndependencies = "
                    f"[{project_requirement!r}]\n",
                    encoding="utf-8",
                )
                self.write_manifest([alpha])
                self.assert_invalid("dependency missing from lock")

    def test_verify_rejects_wheel_requires_python_mismatch(self):
        alpha = self.make_wheel("alpha", "1.0", requires_python=">=3.12")
        self.write_lock([("alpha", "1.0", alpha)])
        self.write_manifest([alpha])

        self.assert_invalid("wheel requires-python")

    def test_verify_rejects_unreachable_locked_distribution(self):
        alpha = self.make_wheel("alpha", "1.0")
        beta = self.make_wheel("beta", "2.0")
        self.write_lock([("alpha", "1.0", alpha), ("beta", "2.0", beta)])
        self.write_manifest([alpha, beta])

        self.assert_invalid("unreachable")

    def test_verify_rejects_oversized_manifest_before_json_decode(self):
        alpha = self.make_wheel("alpha", "1.0")
        self.write_lock([("alpha", "1.0", alpha)])
        manifest = self.wheelhouse / "WHEELHOUSE_MANIFEST.json"
        with manifest.open("wb") as destination:
            destination.truncate(1024 * 1024 + 1)

        self.assert_invalid("size limit")

    def test_release_workflow_builds_and_installs_without_index(self):
        workflow = SCRIPT.parents[1] / ".github" / "workflows" / "release-checks.yml"
        text = workflow.read_text(encoding="utf-8")
        script_text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn('"--require-hashes", "--only-binary=:all:"', script_text)
        self.assertIn("PIP_NO_INDEX: '1'", text)
        self.assertIn("--no-index", text)
        self.assertIn("manylinux_2_34_x86_64", text)
        self.assertIn("actions/upload-artifact@", text)

    def test_manylinux_target_expands_only_to_compatible_lower_glibc_tags(self):
        spec = importlib.util.spec_from_file_location("offline_wheelhouse", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        platforms = module.compatible_platforms("manylinux_2_34_x86_64")

        self.assertEqual(platforms[0], "manylinux_2_34_x86_64")
        self.assertIn("manylinux_2_28_x86_64", platforms)
        self.assertIn("manylinux_2_17_x86_64", platforms)
        self.assertIn("manylinux2014_x86_64", platforms)
        self.assertIn("manylinux1_x86_64", platforms)
        self.assertNotIn("manylinux_2_35_x86_64", platforms)


if __name__ == "__main__":
    unittest.main()
