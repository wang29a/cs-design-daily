#!/usr/bin/env python3
"""Validate one new Markdown lesson, then update the catalog and local build."""
import argparse
import json
import os
from pathlib import Path
import tempfile

from build import ROOT, build


def atomic_write(path, text):
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8',
                                     dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def publish(entry, catalog, content, output):
    previous = catalog.read_text(encoding='utf-8')
    data = json.loads(previous)
    if any(item['date'] == entry['date'] for item in data['lessons']):
        raise ValueError('A complete lesson already exists for this date')
    data['lessons'].append(entry)
    updated = json.dumps(data, ensure_ascii=False, indent=2) + '\n'
    with tempfile.TemporaryDirectory(prefix='.publish-', dir=catalog.parent) as directory:
        stage = Path(directory)
        candidate_catalog = stage / 'catalog.json'
        candidate_catalog.write_text(updated, encoding='utf-8')
        candidate = stage / 'dist'
        manifest = build(candidate, candidate_catalog, content)
        backup = stage / 'old-dist'
        try:
            atomic_write(catalog, updated)
            if output.exists(): output.rename(backup)
            candidate.rename(output)
        except Exception:
            atomic_write(catalog, previous)
            if backup.exists(): backup.rename(output)
            raise
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['date', 'slug', 'title', 'subtitle', 'topic', 'source']:
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--insight', help='A short statement of the core insight')
    args = parser.parse_args()
    entry = {name: getattr(args, name) for name in ['date', 'title', 'subtitle', 'topic', 'source']}
    entry['id'] = args.date + '-' + args.slug
    if args.insight: entry['insight'] = args.insight
    report = publish(entry, ROOT / 'content/catalog.json', ROOT / 'content/lessons', ROOT / 'dist')
    print(json.dumps({'local_built': True, 'public_verified': False,
                      'lessons': report['lessons'], 'latestDate': report['latestDate'],
                      'revision': report['revision']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
