"""Readable labels copied from the same document/card, without AI paraphrasing."""
import re
import urllib.parse

SUBJECT = re.compile(r'^[«"\s]*(?:О|Об)\s+\S', re.I)
HAS_SUBJECT = re.compile(r'\b(?:О|Об)\s+[а-яё]', re.I)
GENERIC = re.compile(r'^(?:Скачать(?: документ| файл)?(?: \([^)]*\))?|Документ(?:\.[a-z]+)?)$', re.I)

def clean(value):
    return ' '.join(value.split()).strip()

def combine(original, subject):
    original, subject = clean(original), clean(subject)
    if not subject or HAS_SUBJECT.search(original) or subject.casefold().strip('«»" .') in original.casefold():
        return original
    return (original + ' — ' + subject)[:1500]

def detail_title(original, text, parse_page):
    """Use explicit document headings, never a random sentence mentioning another act."""
    original = clean(original)
    if HAS_SUBJECT.search(original):
        return original
    # A catalogue may contain many unrelated acts. Its headings cannot describe this act.
    if re.search(r'class=["\'][^"\']*structure-list', text, re.I):
        return original
    body = re.search(r'<(main|article)\b[^>]*>(.*?)</\1>', text, re.I | re.S)
    scope = body[2] if body else text
    headings = [clean(parse_page(h).visible) for h in re.findall(r'<h1\b[^>]*>.*?</h1>', scope, re.I | re.S)]
    if len(headings) == 1 and len(headings[0]) > 20 and (original.casefold() in headings[0].casefold() or headings[0].casefold() in original.casefold()):
        headings += [clean(parse_page(h).visible) for h in re.findall(r'<h2\b[^>]*>.*?</h2>', scope, re.I | re.S)]
    subjects = list(dict.fromkeys(h for h in headings if SUBJECT.match(h) and 20 <= len(h) <= 1400))
    if len(subjects) == 1:
        return subjects[0] if GENERIC.fullmatch(original) else combine(original, subjects[0])
    if GENERIC.fullmatch(original):
        legal = [h for h in headings if re.search(r'\b(?:Приказ|Постановление|Закон|Распоряжение)\b', h, re.I)
                 and (HAS_SUBJECT.search(h) or re.search(r'№\s*\S+', h))]
        if len(legal) == 1:
            return legal[0][:1500]
    return original

def enrich_links(links, text, base, source, parse_page):
    """TFOMS gives the date and full subject next to the attachment in the same card."""
    if source['id'] != 'tfoms':
        return links
    comments = {}
    for block in re.split(r'<div\b[^>]*class=["\']elem["\'][^>]*>', text, flags=re.I)[1:]:
        comment = re.search(r'<div\b[^>]*class=["\']comment["\'][^>]*>(.*?)</div>', block, re.I | re.S)
        if not comment:
            continue
        anchors = parse_page(block[:comment.start()]).links
        subject = parse_page(comment[1]).visible
        if len(anchors) == 1 and re.search(r'к Тарифному соглашению', subject, re.I):
            comments[urllib.parse.urljoin(base, anchors[0][0])] = subject
    for row in links:
        subject = comments.get(row['url'])
        if subject:
            row['original_title'] = row['title']
            row['title'] = combine(row['title'], subject)
    return links
