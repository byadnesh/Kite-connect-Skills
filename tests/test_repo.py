"""Repository hygiene: skill frontmatter, links, shared-file sync, no secrets, unofficial notice."""

import re
import unittest

from _load import ROOT, SKILLS

SKILL_DIRS = sorted(p for p in SKILLS.iterdir() if (p / "SKILL.md").exists())


def frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    return m.group(1) if m else ""


class RepoTests(unittest.TestCase):
    def test_three_skills(self):
        self.assertEqual([p.name for p in SKILL_DIRS], ["kite-backtest", "kite-connect", "kite-options"])

    def test_frontmatter(self):
        for d in SKILL_DIRS:
            fm = frontmatter((d / "SKILL.md").read_text(encoding="utf-8"))
            self.assertTrue(fm, d)
            name = re.search(r"^name:\s*(\S+)", fm, re.M).group(1)
            self.assertEqual(name, d.name)
            self.assertRegex(name, r"^[a-z0-9]+(-[a-z0-9]+)*$")
            desc = re.search(r"^description:\s*>?\s*\n?(.*?)(?=^\w+:|\Z)", fm, re.M | re.S).group(1)
            desc = " ".join(desc.split())
            self.assertLessEqual(len(desc), 1024, d)
            self.assertIn("UNOFFICIAL", desc, d)

    def test_relative_links_resolve(self):
        for md in list(SKILLS.rglob("*.md")) + [ROOT / "README.md"]:
            for target in re.findall(r"\]\(([^)#\s]+)\)", md.read_text(encoding="utf-8")):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                self.assertTrue((md.parent / target).exists(), f"{md.relative_to(ROOT)} → {target}")

    def test_shared_bootstrap_in_sync(self):
        a = (SKILLS / "kite-options" / "scripts" / "kite_common.py").read_bytes()
        b = (SKILLS / "kite-backtest" / "scripts" / "kite_common.py").read_bytes()
        self.assertEqual(a, b, "kite_common.py copies diverged — keep them byte-identical")

    def test_no_hardcoded_credentials(self):
        pattern = re.compile(r"(api_secret|access_token|api_key)\s*=\s*['\"][A-Za-z0-9]{12,}['\"]")
        for f in ROOT.rglob("*.py"):
            if ".git" in f.parts:
                continue
            self.assertIsNone(pattern.search(f.read_text(encoding="utf-8")), f)

    def test_unofficial_notice_everywhere(self):
        for d in SKILL_DIRS:
            self.assertIn("Unofficial", (d / "SKILL.md").read_text(encoding="utf-8"))
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("UNOFFICIAL", readme)
        self.assertTrue((ROOT / "DISCLAIMER.md").exists())


if __name__ == "__main__":
    unittest.main()
