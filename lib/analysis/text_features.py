from __future__ import annotations

import re
import unicodedata

# TODO(perplexity): well-formedness band as additional positive signal.
# Reference: /home/jonas/textalk/dev/lmscore/bin/test_perplexity.py (English path)
# and bin/test_perplexity_llama.py (multilingual via llama.cpp + GGUF).
# Don't default to plain gpt2 — when picking up, evaluate modern small English
# LMs (Pythia 160M/410M, Qwen2.5-0.5B, Llama-3.2-1B) for fluency-band
# discrimination on real comments before locking in a model. Score after
# cheap features so the model loads only when needed.


_NLP = None

_URL_RE = re.compile(r'https?://\S+')
_TIMESTAMP_RE = re.compile(r'\b(?:(\d{1,2}):)?(\d{1,2}):(\d{2})\b')
_EMOJI_RE = re.compile(
    '['
    '\U0001F300-\U0001FAFF'
    '\U0001F600-\U0001F64F'
    '\U00002600-\U000027BF'
    ']'
)
_WORD_RE = re.compile(r"[A-Za-z']+")
_SENT_SPLIT_RE = re.compile(r'[.!?]+\s+|[.!?]+$')
_CITATION_PHRASES = (
    'according to',
    'see also',
    'as described in',
    'as noted in',
    'cited in',
    'referenced in',
)


def _nlp():
    global _NLP
    if _NLP is None:
        import spacy
        _NLP = spacy.load('en_core_web_sm', disable=['lemmatizer', 'attribute_ruler'])
    return _NLP


def entities(text):
    if not text:
        return []
    doc = _nlp()(text)
    return [(ent.label_, ent.text) for ent in doc.ents]


def sentences(text):
    if not text:
        return []
    doc = _nlp()(text)
    return [s.text.strip() for s in doc.sents if s.text.strip()]


def sentence_count(text):
    if not text.strip():
        return 0
    parts = [p for p in _SENT_SPLIT_RE.split(text) if p.strip()]
    return max(len(parts), 1)


def type_token_ratio(text):
    words = [w.lower() for w in _WORD_RE.findall(text)]
    if not words:
        return 0.0
    return len(set(words)) / len(words)


def caps_ratio(text):
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if c.isupper()) / len(letters)


def emoji_density(text):
    if not text:
        return 0.0
    return len(_EMOJI_RE.findall(text)) / len(text)


def punctuation_ratio(text):
    """Fraction of characters in the Unicode 'P' (Punctuation) category —
    Pc (connector), Pd (dash), Pe (close), Pf (final), Pi (initial),
    Po (other), Ps (open). Captures dashes, slashes, semicolons, quotes,
    parentheses, etc. — including non-ASCII variants. Higher in technical
    or carefully-edited prose."""
    if not text:
        return 0.0
    return sum(1 for c in text if unicodedata.category(c).startswith('P')) / len(text)


_TITLE_CASE_RE = re.compile(r'^[A-Z][a-z]')


def mid_sentence_caps_ratio(text):
    """Title-Case mid-sentence occurrences per alphabetic token. spaCy
    handles real sentence boundaries (so 'Mr. Cain', 'i.e.', etc. don't
    falsely terminate). For each sentence, all-but-the-first alphabetic
    token is checked: capitalized + lowercase first letter (excludes
    all-caps acronyms like NPC, USA). Catches mid-sentence proper-noun
    name-dropping: Brotherhood of Steel, Black Isle Studios, etc."""
    if not text or len(text) < 30:
        return 0.0
    doc = _nlp()(text)
    caps = 0
    total = 0
    for sent in doc.sents:
        toks = [t for t in sent if t.is_alpha]
        total += len(toks)
        if len(toks) <= 1:
            continue
        for tok in toks[1:]:
            if _TITLE_CASE_RE.match(tok.text):
                caps += 1
    return caps / total if total else 0.0


def structural_features(text):
    return {
        'length': len(text),
        'sentence_count': sentence_count(text),
        'type_token_ratio': type_token_ratio(text),
        'caps_ratio': caps_ratio(text),
        'emoji_density': emoji_density(text),
        'punctuation_ratio': punctuation_ratio(text),
        'mid_sentence_caps_ratio': mid_sentence_caps_ratio(text),
    }


def has_url(text):
    return bool(_URL_RE.search(text))


def has_citation_marker(text):
    lowered = text.lower()
    return any(phrase in lowered for phrase in _CITATION_PHRASES)


def extract_timestamps(text):
    matches = []
    for m in _TIMESTAMP_RE.finditer(text):
        h, mm, ss = m.group(1), m.group(2), m.group(3)
        if h is not None:
            seconds = int(h) * 3600 + int(mm) * 60 + int(ss)
        else:
            seconds = int(mm) * 60 + int(ss)
        if int(ss) >= 60:
            continue
        matches.append((seconds, m.group(0)))
    return matches
