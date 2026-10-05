import importlib.util
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build


class ContentBuildTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.catalog = self.root / 'catalog.json'
        self.catalog.write_bytes((ROOT / 'content/catalog.json').read_bytes())
        self.content = self.root / 'lessons'
        shutil.copytree(ROOT / 'content/lessons', self.content)
        self.output = self.root / 'dist'

    def tearDown(self):
        self.temporary.cleanup()

    def generate(self):
        return build.build(self.output, self.catalog, self.content)

    def test_content_is_on_independent_pages_and_build_is_deterministic(self):
        first = self.generate()
        self.assertEqual(first, self.generate())
        home = (self.output / 'index.html').read_text()
        self.assertNotIn('累计确认的前沿只能跨过', home)
        for lesson in json.loads(self.catalog.read_text())['lessons']:
            page = self.output / 'lessons' / lesson['id'] / 'index.html'
            self.assertTrue(page.exists())
            self.assertIn(lesson['title'], page.read_text())
            self.assertIn(lesson['id'], home)

    def test_sixth_lesson_enters_home_archive_and_adjacent_navigation(self):
        data = json.loads(self.catalog.read_text())
        item = {**data['lessons'][-1], 'id': '2026-10-06-verification',
                'date': '2026-10-06', 'title': '验证用新讲义'}
        data['lessons'].append(item)
        self.catalog.write_text(json.dumps(data))
        report = self.generate()
        self.assertEqual(report['lessons'], 6)
        self.assertEqual(report['latestId'], item['id'])
        for path in ['index.html', 'archive/index.html',
                     'lessons/2026-10-05-tcp-window/index.html']:
            self.assertIn(item['id'], (self.output / path).read_text())

    def test_duplicate_date_preserves_previous_build(self):
        before = self.generate()
        data = json.loads(self.catalog.read_text())
        data['lessons'].append({**data['lessons'][0], 'id': '2026-10-01-other'})
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            self.generate()
        self.assertEqual(json.loads((self.output / 'manifest.json').read_text()), before)

    def test_missing_source_preserves_previous_page(self):
        self.generate()
        before = (self.output / 'index.html').read_bytes()
        (self.content / '01-unix-pipe.md').unlink()
        with self.assertRaises(FileNotFoundError): self.generate()
        self.assertEqual((self.output / 'index.html').read_bytes(), before)

    def test_source_cannot_escape_content_directory(self):
        data = json.loads(self.catalog.read_text())
        data['lessons'][0]['source'] = '../private.md'
        self.catalog.write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'filename'): self.generate()

    def test_markdown_escapes_markup_and_rejects_unfinished_code(self):
        from markdown import render_markdown
        rendered = render_markdown('# Title\n\n<script>alert(1)</script>\n\n[unsafe](javascript:alert)')
        self.assertNotIn('<script>', rendered)
        self.assertNotIn('href="javascript:', rendered)
        with self.assertRaisesRegex(ValueError, 'unclosed'):
            render_markdown('# Title\n\n```text\nbroken')

    def test_figures_render_on_all_lessons_and_enter_public_manifest(self):
        report = self.generate()
        data = json.loads(self.catalog.read_text())
        referenced = set()
        for lesson in data['lessons']:
            page = (self.output / 'lessons' / lesson['id'] / 'index.html').read_text()
            source = (self.content / lesson['source']).read_text()
            paths = re.findall(r'^!\[[^\]]+\]\((assets/figures/[^)]+)\)$', source, re.MULTILINE)
            self.assertEqual(page.count('<figure class="lesson-figure">'), len(paths))
            for path in paths:
                self.assertIn('src="/cs-design-daily/' + path + '"', page)
                self.assertIn(path, report['files'])
                referenced.add(path)
        figures = [name for name in report['files'] if name.startswith('assets/figures/')]
        self.assertGreaterEqual(len(referenced), 10)
        for name in figures:
            self.assertEqual(report['files'][name], hashlib.sha256((self.output / name).read_bytes()).hexdigest())

    def test_figure_urls_follow_deployment_base(self):
        for base in ['', '/preview', '/cs-design-daily']:
            build.build(self.output, self.catalog, self.content, base=base)
            page = (self.output / 'lessons/2026-10-01-unix-pipe/index.html').read_text()
            self.assertIn('src="' + base + '/assets/figures/pipe-flow.svg"', page)

    def test_invalid_or_missing_figure_preserves_previous_build(self):
        before = self.generate()
        source = self.content / '01-unix-pipe.md'
        original = source.read_text()
        for path in ['https://example.com/private.svg', '../../private.svg',
                     'assets/figures/../../private.svg', 'assets/figures/missing.svg']:
            source.write_text(original.replace('assets/figures/pipe-flow.svg', path))
            with self.assertRaisesRegex(ValueError, 'Figure|Missing figure'):
                self.generate()
            self.assertEqual(json.loads((self.output / 'manifest.json').read_text()), before)

    def test_figure_descriptions_are_escaped_and_required(self):
        from markdown import render_markdown
        body = '# Title\n\n![<script> & "label"](assets/figures/pipe-flow.svg)'
        rendered = render_markdown(body)
        self.assertIn('&lt;script&gt; &amp; &quot;label&quot;', rendered)
        self.assertNotIn('<script>', rendered)
        for image in ['![](assets/figures/pipe-flow.svg)', '![' + ' ' + '](assets/figures/pipe-flow.svg)']:
            with self.assertRaisesRegex(ValueError, 'Figure'):
                render_markdown('# Title\n\n' + image)

    def test_publish_validates_candidate_before_changing_catalog_or_site(self):
        from publish import publish
        self.generate()
        before_catalog = self.catalog.read_bytes()
        before_page = (self.output / 'index.html').read_bytes()
        item = {**json.loads(self.catalog.read_text())['lessons'][-1],
                'id': '2026-10-06-new-lesson', 'date': '2026-10-06',
                'source': 'missing-source.md'}
        with self.assertRaises(FileNotFoundError):
            publish(item, self.catalog, self.content, self.output)
        self.assertEqual(self.catalog.read_bytes(), before_catalog)
        self.assertEqual((self.output / 'index.html').read_bytes(), before_page)
        item['source'] = '05-tcp-window.md'
        report = publish(item, self.catalog, self.content, self.output)
        self.assertEqual(report['lessons'], 6)
        self.assertIn(item['id'], (self.output / 'archive/index.html').read_text())
        with self.assertRaisesRegex(ValueError, 'already exists'):
            publish(item, self.catalog, self.content, self.output)


if __name__ == '__main__':
    unittest.main()
