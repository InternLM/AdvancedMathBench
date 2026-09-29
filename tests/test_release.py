"""Offline checks for the source release, documentation, and download helpers."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from advancedmathbench.backends import validate_config


ROOT = Path(__file__).resolve().parents[1]
DATA_REVISION = "80abe34097edf2531e3d5b07337c4cc0710bfb24"
MODEL_REVISION = "2ad58735622f70bbe2f106049bcdf34f5bb93cfd"


class ReleaseTests(unittest.TestCase):
    def test_example_configs(self):
        expected = {
            "prover_api.example.json": {"policy", "verifier"},
            "verifier_api.example.json": {"verifier"},
            "verifier_meta.example.json": {"verifier", "meta"},
            "local_autoverifier.example.json": {"policy", "verifier"},
        }
        self.assertEqual({p.name for p in (ROOT / "configs").glob("*.example.json")}, set(expected))
        for name, roles in expected.items():
            config = json.loads((ROOT / "configs" / name).read_text())
            self.assertEqual(set(config), roles)
            for spec in config.values():
                validate_config(spec)

    def test_arxiv_citation_and_final_readme_authors(self):
        bib = (ROOT / "citation.bib").read_text().strip()
        readme = (ROOT / "README.md").read_text()
        self.assertIn("```bibtex\n" + bib + "\n```", readme)
        authors = re.search(r"author = \{([^}]+)\}", bib).group(1).split(" and ")
        self.assertEqual(len(authors), 13)
        self.assertNotIn("Zhouqi Hua", authors)
        self.assertEqual(authors[4], "Wenyong Huang")
        cff = (ROOT / "CITATION.cff").read_text()
        pairs = re.findall(r"family-names: ([^\n]+)\n\s+given-names: ([^\n]+)", cff)
        self.assertEqual([given + " " + family for family, given in pairs], authors)
        for author in authors:
            self.assertIn(author, readme.split("## Overview")[0])
        self.assertIn("Zhouqi Hua", readme.split("## Overview")[0])

    def test_local_documentation_links(self):
        docs = [ROOT / "README.md", ROOT / "data/README.md", ROOT / "assets/README.md"]
        docs.extend((ROOT / "docs").glob("*.md"))
        for doc in docs:
            text = doc.read_text()
            links = re.findall(r"\]\(([^\s)]+)\)", text)
            links.extend(re.findall(r'(?:src|href)="([^"]+)"', text))
            for link in links:
                if "://" in link or link.startswith(("#", "mailto:")):
                    continue
                target = link.split("#", 1)[0]
                with self.subTest(document=doc.name, target=target):
                    self.assertTrue((doc.parent / target).is_file())

    def test_pinned_artifacts(self):
        for name, revision in [("download_data.sh", DATA_REVISION), ("download_verifier.sh", MODEL_REVISION)]:
            self.assertIn(revision, (ROOT / "scripts" / name).read_text())
            self.assertIn(revision, (ROOT / "docs/release_notes.md").read_text())
        local = json.loads((ROOT / "configs/local_autoverifier.example.json").read_text())
        self.assertEqual(local["verifier"]["revision"], MODEL_REVISION)
        sums = (ROOT / "data/SHA256SUMS").read_text().splitlines()
        self.assertEqual(len(sums), 2)
        self.assertTrue(all(re.fullmatch(r"[a-f0-9]{64}  data/(proverbench|verifierbench)/test\.jsonl", line) for line in sums))

    @unittest.skipUnless(shutil.which("bash"), "bash not installed")
    def test_shell_syntax(self):
        for script in (ROOT / "scripts").glob("*.sh"):
            subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True)

    @unittest.skipUnless(shutil.which("bash") and shutil.which("sha256sum"), "requires bash and sha256sum")
    def test_data_download_helper_offline(self):
        import hashlib

        with tempfile.TemporaryDirectory(prefix="amb release ") as name:
            root = Path(name)
            (root / "scripts").mkdir()
            (root / "data").mkdir()
            (root / "bin").mkdir()
            shutil.copyfile(ROOT / "scripts/download_data.sh", root / "scripts/download_data.sh")
            payload = b"toy benchmark\n"
            paths = ["data/proverbench/test.jsonl", "data/verifierbench/test.jsonl"]
            (root / "data/SHA256SUMS").write_text("".join(
                hashlib.sha256(payload).hexdigest() + "  " + p + "\n" for p in paths))
            # A local fake hf executable verifies arguments and writes toy files.
            # It never accesses credentials, networks, or the real benchmark.
            fake = root / "bin/hf"
            fake.write_text(
                "#!/usr/bin/env bash\nset -euo pipefail\n"
                '[[ "$1" == download && "$2" == debouter/AdvancedMathBench ]]\n'
                '[[ "$3" == data/proverbench/test.jsonl && "$4" == data/verifierbench/test.jsonl ]]\n'
                '[[ "$5" == --repo-type && "$6" == dataset && "$7" == --revision ]]\n'
                f'[[ "$8" == {DATA_REVISION} && "$9" == --local-dir ]]\n'
                'mkdir -p "${10}/data/proverbench" "${10}/data/verifierbench"\n'
                'printf "toy benchmark\\n" > "${10}/data/proverbench/test.jsonl"\n'
                'printf "toy benchmark\\n" > "${10}/data/verifierbench/test.jsonl"\n'
            )
            fake.chmod(0o755)
            env = dict(os.environ, PATH=str(root / "bin") + os.pathsep + os.environ.get("PATH", ""))
            script = str(root / "scripts/download_data.sh")
            for args, dest in [([], root), ([str(root / "custom destination")], root / "custom destination")]:
                proc = subprocess.run(["bash", script, *args], env=env, text=True, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(proc.stdout.count(": OK"), 2)
                self.assertEqual((dest / paths[0]).read_bytes(), payload)
            (root / "data/SHA256SUMS").write_text("0" * 64 + "  " + paths[0] + "\n")
            proc = subprocess.run(["bash", script], env=env, text=True, capture_output=True)
            self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
