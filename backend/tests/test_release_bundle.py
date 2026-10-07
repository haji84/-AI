"""Release bundle tests use synthetic text only and never read operational data."""
from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_release_bundle.py"
SOURCES = {
    ".gitignore": b".env\n",
    "AGENTS.md": b"Synthetic project constraints.\n",
    "README.md": b"Synthetic release source.\n",
    "PROJECT_STATE.md": b"Release candidate; external gates pending.\n",
    "backend/.env.example": b"DATABASE_URL=postgresql://example.invalid/test\n",
    "backend/pyproject.toml": b"[project]\nname = 'synthetic'\n",
    "backend/app/main.py": b"# synthetic app\n",
    "backend/app/db.py": b"# synthetic database access\n",
    "backend/app/migrations.py": b"# synthetic migration runner\n",
    "db/schema_phase0_draft.sql": b"-- synthetic schema\n",
    "db/migrations/001_initial.sql": b"SELECT 1;\n",
    "docs/SPECIFICATION.md": b"Synthetic specification.\n",
    "docs/phase1/LAN_DEPLOYMENT.md": b"Synthetic deployment instructions.\n",
    "docs/architecture/TENANT_OPERATIONS.md": b"Synthetic tenant instructions.\n",
    "deploy/systemd/fire-ai.service": b"[Service]\nExecStart=/example/server\n",
    "deploy/nginx/fire-ai.conf": b"# synthetic proxy config\n",
    "deploy/windows/start-fire-ai.cmd": b"@echo synthetic\n",
    "frontend/index.html": b"<!doctype html><title>Synthetic</title>\n",
    "scripts/migrate_database.py": b"print('synthetic')\n",
}


class ReleaseBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        for name, data in SOURCES.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (self.repo / "scripts/migrate_database.py").chmod(0o755)
        self.commit()
        self.commit_sha = self.git("rev-parse", "HEAD").strip()
        self.tree_sha = self.git("rev-parse", "HEAD^{tree}").strip()
        self.output = self.base / "release.tar.gz"

    def git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.repo), "-c", "user.name=Synthetic Test",
             "-c", "user.email=synthetic@example.invalid", *args],
            capture_output=True, text=True, check=True,
        )
        return result.stdout

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-qm", "synthetic fixture")

    def cli(self, *args):
        return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)],
                              capture_output=True, text=True)

    def build(self, output=None, ref=None):
        return self.cli("build", "--repo", self.repo, "--ref", ref or self.commit_sha,
                        "--release-id", "test-rc.1", "--output", output or self.output)

    def assert_built(self):
        result = self.build()
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def read_bundle(self):
        with tarfile.open(self.output, "r:gz") as archive:
            return [(info, archive.extractfile(info).read()) for info in archive]

    def rewrite(self, entries):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for info, data in entries:
                archive.addfile(info, io.BytesIO(data))
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode="wb", filename="", mtime=0) as archive:
            archive.write(stream.getvalue())
        self.output.write_bytes(compressed.getvalue())

    def assert_invalid(self):
        result = self.cli("verify", self.output)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("error:", result.stderr.lower())
        self.assertNotIn("Traceback", result.stderr)

    def test_build_is_deterministic_and_manifest_identifies_committed_source(self):
        self.assert_built()
        second = self.base / "second.tar.gz"
        result = self.build(second)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.output.read_bytes(), second.read_bytes())
        entries = self.read_bundle()
        self.assertEqual([info.name for info, _ in entries], sorted(info.name for info, _ in entries))
        files = dict((info.name, data) for info, data in entries)
        manifest = json.loads(files.pop("RELEASE_MANIFEST.json"))
        self.assertEqual(manifest["commit"], self.commit_sha)
        self.assertEqual(manifest["tree"], self.tree_sha)
        self.assertEqual(manifest["release_id"], "test-rc.1")
        self.assertEqual(manifest["status"], "release-candidate")
        self.assertIs(manifest["production_ready"], False)
        self.assertEqual(files, SOURCES)
        self.assertEqual(set(manifest["files"]), set(SOURCES))
        for name, data in SOURCES.items():
            entry = manifest["files"][name]
            self.assertEqual(entry["sha256"], hashlib.sha256(data).hexdigest())
            self.assertEqual(entry["size"], len(data))
            self.assertEqual(entry["mode"], "100755" if name.startswith("scripts/") else "100644")
        result = self.cli("verify", self.output, "--expected-commit", self.commit_sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("not authenticity", result.stdout)

    def test_uses_committed_bytes_and_ignores_dirty_and_untracked_secrets(self):
        (self.repo / "README.md").write_text("DIRTY WORKTREE SECRET")
        (self.repo / "backend/.env").write_text("PASSWORD=untracked-secret")
        (self.repo / "credentials.json").write_text('{"secret":"untracked"}')
        self.assert_built()
        files = {info.name: data for info, data in self.read_bundle()}
        self.assertEqual(files["README.md"], SOURCES["README.md"])
        self.assertNotIn("backend/.env", files)
        self.assertNotIn("credentials.json", files)

    def test_resolves_ref_to_fixed_commit(self):
        result = self.build(ref="HEAD")
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = json.loads(dict((i.name, d) for i, d in self.read_bundle())["RELEASE_MANIFEST.json"])
        self.assertEqual(manifest["commit"], self.commit_sha)

    def test_rejects_unsafe_tracked_paths(self):
        for path in ("backend/.env", "backend/.env.production", "backend/runtime/config.json",
                     "backend/storage/report.txt", "docs/originals/report.txt", "db/backup.sql",
                     "backend/credentials.json", "backend/private.pem", "uploads/report.txt",
                     "frontend/photo.jpg", "backend/data/customer.csv"):
            with self.subTest(path=path):
                target = self.repo / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("synthetic sensitive sentinel")
                self.git("add", "-f", path)
                self.git("commit", "-qm", "unsafe fixture")
                result = self.build(ref="HEAD")
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn(path, result.stderr)
                self.assertFalse(self.output.exists())
                self.git("rm", "-q", path)
                self.git("commit", "-qm", "remove unsafe fixture")

    def test_rejects_tracked_symlink(self):
        (self.repo / "backend/app/link.py").symlink_to("main.py")
        self.commit()
        result = self.build(ref="HEAD")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend/app/link.py", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_gitlink_submodule(self):
        self.git("update-index", "--add", "--cacheinfo", f"160000,{self.commit_sha},backend/vendor")
        self.git("commit", "-qm", "gitlink fixture")
        result = self.build(ref="HEAD")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend/vendor", result.stderr)

    def test_rejects_binary_data_in_text_extension(self):
        (self.repo / "backend/app/binary.py").write_bytes(b"secret\0bytes\xff")
        self.commit()
        result = self.build(ref="HEAD")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("backend/app/binary.py", result.stderr)

    def test_rejects_missing_required_source_and_migrations(self):
        for path in ("frontend/index.html", "db/migrations/001_initial.sql"):
            with self.subTest(path=path):
                self.git("rm", path)
                self.git("commit", "-qm", "missing required fixture")
                result = self.build(ref="HEAD")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("required", result.stderr.lower())
                self.assertFalse(self.output.exists())
                self.git("reset", "--hard", self.commit_sha)

    def test_never_overwrites_existing_output(self):
        self.output.write_bytes(b"keep me")
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"keep me")

    def test_rejects_corrupt_gzip(self):
        self.assert_built()
        data = bytearray(self.output.read_bytes())
        data[len(data) // 2] ^= 255
        self.output.write_bytes(data)
        self.assert_invalid()

    def test_rejects_changed_source_bytes(self):
        self.assert_built()
        entries = self.read_bundle()
        for info, data in entries:
            if info.name == "README.md":
                changed = b"x" * len(data)
                entries[entries.index((info, data))] = (info, changed)
                break
        self.rewrite(entries)
        self.assert_invalid()

    def test_rejects_extra_missing_duplicate_and_traversal_members(self):
        self.assert_built()
        original = self.read_bundle()
        for mutation in ("extra", "missing", "duplicate", "traversal", "absolute", "link"):
            with self.subTest(mutation=mutation):
                entries = list(original)
                info = tarfile.TarInfo("backend/app/extra.py")
                data = b"# unexpected\n"
                info.size = len(data)
                if mutation == "extra":
                    entries.append((info, data))
                elif mutation == "missing":
                    entries = [(i, d) for i, d in entries if i.name != "README.md"]
                elif mutation == "duplicate":
                    entries.append(entries[0])
                elif mutation == "traversal":
                    info.name = "../escape.py"
                    entries.append((info, data))
                elif mutation == "absolute":
                    info.name = "/escape.py"
                    entries.append((info, data))
                elif mutation == "link":
                    info.type = tarfile.SYMTYPE
                    info.linkname = "README.md"
                    info.size = 0
                    entries.append((info, b""))
                self.rewrite(entries)
                self.assert_invalid()
        self.assertFalse((self.base / "escape.py").exists())

    def test_rejects_wrong_manifest_metadata(self):
        self.assert_built()
        original = self.read_bundle()
        for field, value in (("production_ready", True), ("status", "production-ready"),
                             ("commit", "not-a-sha"), ("tree", 42),
                             ("release_id", "../unsafe"), ("schema_version", 99)):
            with self.subTest(field=field):
                entries = []
                for info, data in original:
                    if info.name == "RELEASE_MANIFEST.json":
                        manifest = json.loads(data)
                        manifest[field] = value
                        data = json.dumps(manifest).encode()
                        info = tarfile.TarInfo(info.name)
                        info.size = len(data)
                    entries.append((info, data))
                self.rewrite(entries)
                self.assert_invalid()

    def test_rejects_wrong_file_metadata(self):
        self.assert_built()
        original = self.read_bundle()
        for field, value in (("size", True), ("mode", "100777"), ("sha256", "bad")):
            with self.subTest(field=field):
                entries = []
                for info, data in original:
                    if info.name == "RELEASE_MANIFEST.json":
                        manifest = json.loads(data)
                        manifest["files"]["README.md"][field] = value
                        data = json.dumps(manifest).encode()
                        info = tarfile.TarInfo(info.name)
                        info.size = len(data)
                    entries.append((info, data))
                self.rewrite(entries)
                self.assert_invalid()

    def test_rejects_expected_commit_mismatch(self):
        self.assert_built()
        result = self.cli("verify", self.output, "--expected-commit", "0" * 40)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("commit", result.stderr)

    def test_rejects_noncanonical_tar_metadata_and_trailing_payload(self):
        self.assert_built()
        pristine = self.output.read_bytes()
        entries = self.read_bundle()
        entries[0][0].uid = 1000
        self.rewrite(entries)
        self.assert_invalid()
        self.output.write_bytes(pristine + gzip.compress(b"hidden payload", mtime=0))
        self.assert_invalid()

    def rewrite_manifest(self, change, entries=None):
        changed_entries = []
        for info, data in entries or self.read_bundle():
            if info.name == "RELEASE_MANIFEST.json":
                manifest = json.loads(data)
                change(manifest)
                data = (json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
                info = copy.copy(info)
                info.size = len(data)
            changed_entries.append((info, data))
        self.rewrite(changed_entries)

    def test_rejects_valid_shaped_wrong_tree_id(self):
        self.assert_built()
        self.rewrite_manifest(lambda manifest: manifest.update(tree="0" * 40))
        result = self.cli("verify", self.output)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("tree", result.stderr)

    def test_rejects_changed_source_with_corrected_manifest_digest_but_original_tree(self):
        self.assert_built()
        entries = []
        changed = b"Tampered bytes with a recomputed checksum.\n"
        for info, data in self.read_bundle():
            if info.name == "README.md":
                info = copy.copy(info)
                info.size = len(changed)
                data = changed
            entries.append((info, data))
        def change(manifest):
            manifest["files"]["README.md"]["sha256"] = hashlib.sha256(changed).hexdigest()
            manifest["files"]["README.md"]["size"] = len(changed)
        self.rewrite_manifest(change, entries)
        result = self.cli("verify", self.output)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("tree", result.stderr)

    def test_verifies_sha256_git_repository_and_git_tree_sort_order(self):
        self.repo = self.base / "sha256-repo"
        self.repo.mkdir()
        self.git("init", "-q", "--object-format=sha256")
        for name, data in {**SOURCES, "backend/app/a.py": b"# one\n",
                           "backend/app/a/z.py": b"# two\n",
                           "backend/app/a0.py": b"# three\n"}.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.commit()
        self.commit_sha = self.git("rev-parse", "HEAD").strip()
        self.tree_sha = self.git("rev-parse", "HEAD^{tree}").strip()
        self.assertEqual(len(self.commit_sha), 64)
        self.assert_built()
        result = self.cli("verify", self.output, "--expected-commit", self.commit_sha)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.rewrite_manifest(lambda manifest: manifest.update(tree="0" * 64))
        self.assert_invalid()

    def test_rejects_duplicate_json_keys_and_malformed_manifest(self):
        self.assert_built()
        original = self.read_bundle()
        for replacement in (b'{"commit":"a","commit":"b"}', b'{broken', b'[]'):
            with self.subTest(replacement=replacement):
                entries = []
                for info, data in original:
                    if info.name == "RELEASE_MANIFEST.json":
                        info = copy.copy(info)
                        info.size = len(replacement)
                        data = replacement
                    entries.append((info, data))
                self.rewrite(entries)
                self.assert_invalid()

    def test_rejects_deeply_nested_manifest_without_traceback(self):
        self.assert_built()
        replacement = ("[" * 10000 + "0" + "]" * 10000).encode()
        entries = []
        for info, data in self.read_bundle():
            if info.name == "RELEASE_MANIFEST.json":
                info = copy.copy(info)
                info.size = len(replacement)
                data = replacement
            entries.append((info, data))
        self.rewrite(entries)
        self.assert_invalid()

    def test_rejects_existing_symlink_output(self):
        existing = self.base / "keep.txt"
        existing.write_bytes(b"keep me")
        self.output.symlink_to(existing)
        result = self.build()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(existing.read_bytes(), b"keep me")

    def test_partial_clone_fails_without_fetching_missing_local_blobs(self):
        self.git("config", "uploadpack.allowFilter", "true")
        clone = self.base / "partial-clone"
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", "--no-checkout",
                        self.repo.as_uri(), str(clone)], check=True, capture_output=True)
        trace = self.base / "git-trace.log"
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "build", "--repo", str(clone),
             "--ref", self.commit_sha, "--release-id", "test-rc.1", "--output", str(self.output)],
            capture_output=True, text=True, env={**os.environ, "GIT_TRACE": str(trace)},
        )
        self.assertNotIn("built-in: git fetch", trace.read_text())
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("Git source read failed", result.stderr)
        self.assertFalse(self.output.exists())

    def test_rejects_invalid_ref_and_release_id_without_output(self):
        result = self.build(ref="no-such-ref")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        result = self.cli("build", "--repo", self.repo, "--ref", self.commit_sha,
                          "--release-id", "../escape", "--output", self.output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
