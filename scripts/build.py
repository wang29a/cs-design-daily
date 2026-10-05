#!/usr/bin/env python3
"""Generate a static reading journal from independent Markdown sources."""
import argparse
from collections import Counter
import datetime
import hashlib
import html
import json
import math
from pathlib import Path
import re
import shutil
import tempfile

from markdown import render_markdown

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://wang29a.github.io'


def escape(value):
    return html.escape(str(value), quote=True)


def template(name, values):
    source = (ROOT / 'templates' / (name + '.html')).read_text(encoding='utf-8')
    def replace(match):
        key = match[1]
        if key not in values:
            raise ValueError('Missing template value: ' + key)
        return str(values[key])
    return re.sub(r'\{\{([a-z_]+)\}\}', replace, source)


def collect(catalog, content):
    entries = json.loads(catalog.read_text(encoding='utf-8'))['lessons']
    if not isinstance(entries, list) or not entries:
        raise ValueError('Catalog must contain at least one lesson')
    seen_ids, seen_dates, lessons = set(), set(), []
    for entry in entries:
        for key in ('id', 'date', 'title', 'subtitle', 'topic', 'source'):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError('Missing field: ' + key)
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}-[a-z0-9-]+', entry['id']):
            raise ValueError('Invalid lesson id')
        if datetime.date.fromisoformat(entry['date']).isoformat() != entry['date']:
            raise ValueError('Invalid date')
        if not entry['id'].startswith(entry['date'] + '-'):
            raise ValueError('Lesson id must start with its date')
        if entry['id'] in seen_ids or entry['date'] in seen_dates:
            raise ValueError('Duplicate lesson id or date')
        seen_ids.add(entry['id']); seen_dates.add(entry['date'])
        name = Path(entry['source'])
        if name.name != entry['source'] or name.suffix != '.md':
            raise ValueError('Source must be a Markdown filename')
        source = (content / name).resolve()
        if source.parent != content.resolve():
            raise ValueError('Source escapes content directory')
        body = source.read_text(encoding='utf-8')
        if not body.startswith('# '):
            raise ValueError('Lesson must begin with a Markdown title')
        paragraphs = body.split('\n\n')
        excerpt = next((p for p in paragraphs if not p.startswith('#') and p.strip()), '')
        excerpt = re.sub(r'^这篇补上[^。]+。', '', excerpt)
        excerpt = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', excerpt)
        excerpt = excerpt.replace('\n', ' ').replace('`', '')
        if len(excerpt) > 95:
            excerpt = excerpt[:94].rstrip('，、； ') + '…'
        chars = len(re.findall(r'[\u3400-\u9fff]|[A-Za-z0-9]+', body))
        lessons.append({**entry, 'body': render_markdown(body), 'excerpt': excerpt,
                        'minutes': max(1, math.ceil(chars / 230)),
                        'sources': len(re.findall(r'\]\(https?://', body)),
                        'characters': chars})
    lessons.sort(key=lambda entry: entry['date'])
    for number, lesson in enumerate(lessons, 1): lesson['number'] = number
    return lessons


def row(lesson, base, legacy=False):
    url = base + '/lessons/' + lesson['id'] + '/'
    compatibility = ' data-legacy-id="' + lesson['id'] + '"' if legacy else ''
    return ('<a class="lesson-row" href="' + url + '" data-lesson-topic="' + escape(lesson['topic']) + '"' + compatibility + '>'
            '<time datetime="' + lesson['date'] + '">' + lesson['date'].replace('-', '.') + '</time>'
            '<span><strong class="row-title">' + escape(lesson['title']) + '</strong>'
            '<span class="row-subtitle">' + escape(lesson['subtitle']) + '</span></span>'
            '<span class="row-end">' + escape(lesson['topic']) + '<i aria-hidden="true">↗</i></span></a>')


def generate(output, catalog=None, content=None, base='/cs-design-daily'):
    if base and not re.fullmatch(r'/[a-zA-Z0-9/_-]+', base):
        raise ValueError('Invalid deployment base path')
    base = base.rstrip('/')
    lessons = collect(catalog or ROOT / 'content/catalog.json', content or ROOT / 'content/lessons')
    latest = lessons[-1]
    common = {'base': base, 'latest_date': latest['date'].replace('-', '.'),
              'home_current': '', 'archive_current': ''}
    def page(name, title, description, values, path, kind):
        inner = template(name, {**common, **values})
        full = template('base', {**common, 'title': escape(title), 'description': escape(description),
                        'canonical': ORIGIN + base + '/' + path,
                        'page_type': kind, 'content': inner,
                        'home_current': 'aria-current="page"' if kind == 'home' else '',
                        'archive_current': 'aria-current="page"' if kind == 'archive' else ''})
        target = output / path / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(full, encoding='utf-8')
    counts = Counter(lesson['topic'] for lesson in lessons)
    latest_url = base + '/lessons/' + latest['id'] + '/'
    page('home', '今日阅读', '每天认真吃透一个计算机系统设计。完整讲义、贯穿推演与原始来源。', {
        'count': len(lessons), 'latest_topic': escape(latest['topic']),
        'latest_number': f"{latest['number']:02d}", 'latest_title': escape(latest['title']),
        'latest_subtitle': escape(latest['subtitle']), 'latest_excerpt': escape(latest['excerpt']),
        'latest_minutes': latest['minutes'], 'latest_sources': latest['sources'],
        'latest_insight': escape(latest.get('insight', latest['subtitle'])), 'latest_url': latest_url,
        'recent_rows': ''.join(row(lesson, base) for lesson in list(reversed(lessons[:-1]))[:4]),
        'legacy_links': ''.join('<a data-legacy-id="' + lesson['id'] + '" href="' + base + '/lessons/' + lesson['id'] + '/"></a>' for lesson in lessons),
    }, '', 'home')
    page('archive', '讲义归档', '按日期与领域回看每一篇系统设计讲义。', {
        'count': len(lessons), 'topic_count': len(counts),
        'topic_buttons': ''.join('<button type="button" data-topic="' + escape(topic) + '" aria-pressed="false">' + escape(topic) + '<span>' + str(count) + '</span></button>' for topic, count in counts.items()),
        'archive_rows': ''.join(row(lesson, base) for lesson in reversed(lessons)),
    }, 'archive/', 'archive')
    for index, lesson in enumerate(lessons):
        adjacent = []
        for offset, name, label in [(-1, 'previous', '前一讲'), (1, 'next', '后一讲')]:
            other = index + offset
            if 0 <= other < len(lessons):
                item = lessons[other]
                adjacent.append('<a class="' + name + '" href="' + base + '/lessons/' + item['id'] + '/"><small>' + label + ' · ' + item['date'].replace('-', '.') + '</small><strong>' + escape(item['title']) + '</strong></a>')
        page('article', lesson['title'], lesson['subtitle'], {
            'lesson_title': escape(lesson['title']), 'subtitle': escape(lesson['subtitle']),
            'topic': escape(lesson['topic']), 'date': lesson['date'].replace('-', '.'),
            'number': f"{lesson['number']:02d}", 'minutes': lesson['minutes'],
            'sources': lesson['sources'], 'body': lesson['body'], 'adjacent': ''.join(adjacent),
            'source_url': 'https://github.com/wang29a/cs-design-daily/blob/main/content/lessons/' + lesson['source'],
        }, 'lessons/' + lesson['id'] + '/', 'article')
    shutil.copytree(ROOT / 'assets', output / 'assets', dirs_exist_ok=True)
    public = [{key: value for key, value in lesson.items() if key != 'body'} for lesson in lessons]
    (output / 'data').mkdir(exist_ok=True)
    (output / 'data/catalog.json').write_text(json.dumps({'lessons': public}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (output / '.nojekyll').write_text('')
    not_found = '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>讲义尚未收录</title><h1>这篇讲义尚未收录。</h1><p><a href="' + base + '/archive/">回到讲义归档</a></p></html>'
    (output / '404.html').write_text(not_found, encoding='utf-8')
    files = {path.relative_to(output).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in sorted(output.rglob('*')) if path.is_file()}
    revision = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    manifest = {'revision': revision, 'lessons': len(lessons), 'latestDate': latest['date'],
                'latestId': latest['id'], 'files': files}
    (output / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return manifest


def build(output, catalog=None, content=None, base='/cs-design-daily'):
    output = output.resolve()
    if output == ROOT or ROOT.is_relative_to(output):
        raise ValueError('Build output must not replace the project root')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.build-', dir=output.parent) as temporary:
        candidate = Path(temporary) / 'dist'
        candidate.mkdir()
        manifest = generate(candidate, catalog, content, base)
        # Leave a prior successful output intact until all validation/rendering succeeds.
        previous = output.with_name(output.name + '.previous')
        if previous.exists(): shutil.rmtree(previous)
        if output.exists(): output.rename(previous)
        try:
            candidate.rename(output)
        except Exception:
            if previous.exists(): previous.rename(output)
            raise
        if previous.exists(): shutil.rmtree(previous)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    parser.add_argument('--base-path', default='/cs-design-daily')
    parser.add_argument('--catalog', type=Path)
    parser.add_argument('--content-dir', type=Path)
    args = parser.parse_args()
    report = build(args.output, args.catalog, args.content_dir, args.base_path)
    print(json.dumps({key: report[key] for key in ['revision', 'lessons', 'latestDate', 'latestId']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
