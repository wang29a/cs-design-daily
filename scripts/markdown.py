"""Safe Markdown subset used by the lecture sources."""
import html
import re
from urllib.parse import urlsplit

TOKEN = re.compile(r"(`[^`\n]+`|\*\*[^*\n]+\*\*|\[[^\]\n]+\]\([^\s)]+\))")


def inline(text):
    chunks = []
    for part in TOKEN.split(text):
        if part.startswith('`') and part.endswith('`'):
            chunks.append('<code>' + html.escape(part[1:-1]) + '</code>')
        elif part.startswith('**') and part.endswith('**'):
            chunks.append('<strong>' + html.escape(part[2:-2]) + '</strong>')
        elif part.startswith('['):
            match = re.fullmatch(r'\[([^\]]+)\]\(([^)]+)\)', part)
            if match and urlsplit(match[2]).scheme in ('http', 'https'):
                label, url = match.groups()
                chunks.append('<a href="' + html.escape(url, quote=True) +
                              '" target="_blank" rel="noopener noreferrer">' +
                              html.escape(label) + '</a>')
            else:
                chunks.append(html.escape(part))
        else:
            chunks.append(html.escape(part))
    return ''.join(chunks)


def render_markdown(text):
    output, paragraph, code = [], [], []
    in_code = False
    removed_title = False

    def flush():
        if paragraph:
            output.append('<p>' + inline(' '.join(paragraph)) + '</p>')
            paragraph.clear()

    for line in text.splitlines():
        if line.startswith('```'):
            flush()
            if in_code:
                output.append('<pre tabindex="0"><code>' +
                              html.escape('\n'.join(code)) + '</code></pre>')
                code.clear()
            in_code = not in_code
        elif in_code:
            code.append(line)
        elif not line.strip():
            flush()
        elif re.match(r'^#{1,6} ', line):
            flush()
            level, title = line.split(' ', 1)
            if len(level) == 1 and not removed_title:
                removed_title = True
                continue
            depth = min(max(len(level), 2), 6)
            output.append(f'<h{depth}>' + inline(title) + f'</h{depth}>')
        else:
            paragraph.append(line.strip())
    flush()
    if in_code:
        raise ValueError('Markdown contains an unclosed code fence')
    if not output:
        raise ValueError('Lesson body is empty')
    return '\n'.join(output)
