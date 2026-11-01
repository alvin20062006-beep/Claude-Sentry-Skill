import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('cst_package', ROOT / 'tools/package.py')
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


class Packaging(unittest.TestCase):
    def test_full_package_includes_hidden_manifest_and_matching_checksums(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'full.zip'
            package.build(archive)
            with zipfile.ZipFile(archive) as z:
                prefix = 'Claude-Sentry-Skill/'
                names = set(z.namelist())
                self.assertIn(prefix + '.claude-plugin/plugin.json', names)
                self.assertIn(prefix + 'LICENSE', names)
                self.assertIn(prefix + '.claude-plugin/marketplace.json', names)
                self.assertIn(prefix + '.claude-plugin/icon.png', names)
                self.assertIn(prefix + 'README.en.md', names)
                self.assertIn(prefix + 'docs/index.html', names)
                self.assertIn(prefix + 'docs/assets/banner.svg', names)
                self.assertIn(prefix + 'hooks/hooks.json', names)
                self.assertIn(prefix + 'skills/claude-sentry-skill/SKILL.md', names)
                self.assertFalse(any(name.endswith(('.zip', '.pyc')) for name in names))
                for line in z.read(prefix + 'SHA256SUMS.txt').decode().splitlines():
                    digest, name = line.split('  ', 1)
                    self.assertEqual(digest, hashlib.sha256(z.read(prefix + name)).hexdigest())

    def test_standalone_skill_is_self_contained(self):
        with tempfile.TemporaryDirectory() as temp:
            archive = Path(temp) / 'skill.zip'
            package.build(archive, skill=True)
            with zipfile.ZipFile(archive) as z:
                names = set(z.namelist())
                self.assertIn('claude-sentry-skill/SKILL.md', names)
                self.assertEqual((ROOT / 'LICENSE').read_bytes(), z.read('claude-sentry-skill/LICENSE'))
                self.assertEqual(5, len([name for name in names if '/references/' in name]))
                self.assertFalse(any('/hooks/' in name or '/.claude/' in name for name in names))

    def test_skill_references_and_manifest_version(self):
        manifest = json.loads((ROOT / '.claude-plugin/plugin.json').read_text(encoding='utf-8'))
        self.assertEqual('0.9.1', manifest['version'])
        skill = ROOT / 'skills/claude-sentry-skill'
        text = (skill / 'SKILL.md').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('---\nname: claude-sentry-skill\n'))
        for filename in ('POLICY_INDEX.json', 'SCENARIOS.json', 'PREBAN_EVIDENCE.json',
                         'context_rules.json', 'supported_regions.json'):
            self.assertIn('references/' + filename, text)
            self.assertTrue((skill / 'references' / filename).is_file())


if __name__ == '__main__':
    unittest.main()
