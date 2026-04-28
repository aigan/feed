from __future__ import annotations

import json
import re
from datetime import datetime

from analysis import text_features
from context import Context
from util import dump_json
from youtube import Channel, Subscription, Video

SCHEMA_VERSION = 10

# Cheap-quality gate: triggers author-metadata fetch and excludes the comment
# from 'ignorable'. Any one is sufficient.
MIN_QUALITY_LEN = 200

# Quality-class score boundary (after gate passes and no anti-signal).
QUALITY_SCORE_THRESHOLD = 5

# Creator interaction: any reply/comment from the creator is positive,
# stronger when there's actual content.
CREATOR_STRONG_LEN = 25

# TODO(topic-profile): Tier 2 — author covers same topics as this video.
# Requires data/youtube/channels/active/<id>/topics.json built from
# (a) channel description NER, (b) sample of last ~50 uploads' titles+descriptions,
# (c) per-video CONCEPTS/ENTITIES from ytapi_extracted.json. Compare with Jaccard
# over top-50 entities. The author tier check below would gain a 'topic_match'
# tier above 'known' but below 'subscribed'.

# TODO(cross-video-text-reuse): detect harvested/remixed comment fragments by
# building a minhash/LSH index over comment text across all videos in the
# corpus. Comments whose substantive paragraphs appear verbatim or near-verbatim
# under unrelated videos are engagement-farm spam. Big-precision negative
# signal once the index exists. Index would live alongside per-video data,
# updated incrementally as comments are mirrored.

# Pinning and creator-heart aren't exposed by the YouTube Data API in a usable
# form (viewerRating reflects the *requesting* user's rating, not the channel
# owner's heart; isPinned isn't a field). Creator interaction is detected
# purely via author_channel_id == video.channel_id.
#
# TODO(creator-heart): if YouTube ever exposes "creator hearted this comment"
# via the API (or via an authenticated proxy), add it as a strong positive
# signal — a creator-hearted comment is curated by the video author and
# should be treated similarly to a creator reply.

# Entity types that count as 'novel referents' for scoring. Excludes CARDINAL,
# ORDINAL, QUANTITY, PERCENT, MONEY, DATE, TIME — these don't introduce people,
# works, or things worth lifting into the extractor.
_REFERENT_LABELS = frozenset({
    'PERSON', 'ORG', 'GPE', 'LOC', 'WORK_OF_ART',
    'EVENT', 'PRODUCT', 'FAC', 'NORP', 'LAW', 'LANGUAGE',
})


# Piecewise-linear effort curve. Length anchors → points. Negative for short
# filler ("first!", "lol"), peak at 600 chars (one well-developed paragraph),
# plateau at peak above. Long content isn't penalized for being long; the
# distinguishing work between "wall-of-text bot" and "long thoughtful post"
# is done by the technicality, author, and engagement signals.
_EFFORT_CURVE = [
    (60, -5), (80, -4), (100, -3), (120, -2), (140, -1), (160, 0),
    (200, 1), (300, 2), (400, 3), (500, 4), (600, 5),
]


def _effort_band_points(length):
    if length < _EFFORT_CURVE[0][0]:
        return _EFFORT_CURVE[0][1]
    if length >= _EFFORT_CURVE[-1][0]:
        return _EFFORT_CURVE[-1][1]
    for i in range(1, len(_EFFORT_CURVE)):
        x1, y1 = _EFFORT_CURVE[i]
        if length <= x1:
            x0, y0 = _EFFORT_CURVE[i - 1]
            t = (length - x0) / (x1 - x0)
            return round(y0 + t * (y1 - y0), 1)
    return _EFFORT_CURVE[-1][1]


# Technicality: heuristic signal for analytical/idea-presenting writing.
# Four independent components, each shown as its own breakdown row. Each is
# scaled linearly with anchors taken from the corpus distribution: lo (p25
# or natural floor) → 0 points, hi (p99) → 2.5 points. All four together
# cap at 10 — a comment at p99 in every feature.
_DISCOURSE_RE = re.compile(
    r'\b(?:i\.?e\.?|e\.?g\.?|namely|specifically|'
    r'in particular|in other words|in essence|'
    r'for example|for instance|such as|'
    r'however|moreover|furthermore|nevertheless|'
    r'therefore|thus|hence|'
    r'including but not limited to|by contrast|by definition|'
    r'as a matter of|in nature|fundamentally)\b',
    flags=re.IGNORECASE,
)
_SPECIAL_PUNCT = ';—–/_"'
_WORD_TOKEN_RE = re.compile(r"[A-Za-z']+")
_TECH_MAX_PER_COMPONENT = 2.5
# (p50, p99) anchors per component. p50 → 0 pts (median is "not exceptional"),
# p99 → max pts. Curve is quadratic between — the rise is slow at first and
# steepens toward the top, so only genuinely exceptional values score high.
# tech_special_punct uses the *ratio* (count / length), not raw count, so
# longer comments need proportionally more punctuation to score.
_TECH_ANCHORS = {
    'tech_word_length':         (4.59, 5.23),
    'tech_sentence_length':     (22, 51),
    'tech_discourse_markers':   (0, 3),
    'tech_special_punct_ratio': (0, 0.0194),
}


def _scale(value, lo, hi):
    if value <= lo:
        return 0.0
    if value >= hi:
        return _TECH_MAX_PER_COMPONENT
    t = (value - lo) / (hi - lo)
    return _TECH_MAX_PER_COMPONENT * t * t


def _technicality_contributions(text, sentence_count):
    if len(text) < 200 or sentence_count < 1:
        return []
    words = _WORD_TOKEN_RE.findall(text)
    if not words:
        return []

    avg_word_len = sum(len(w) for w in words) / len(words)
    avg_words_per_sent = len(words) / sentence_count
    markers = len(_DISCOURSE_RE.findall(text))
    special_count = sum(1 for c in text if c in _SPECIAL_PUNCT)
    special_ratio = special_count / len(text)

    contributions = []
    for signal, raw, note in [
        ('tech_word_length', avg_word_len, f'avg word len {avg_word_len:.2f}'),
        ('tech_sentence_length', avg_words_per_sent, f'{avg_words_per_sent:.0f} words/sentence'),
        ('tech_discourse_markers', markers, f'{markers} discourse markers'),
        ('tech_special_punct_ratio', special_ratio,
            f'{special_count} special punct / {len(text)} chars = {special_ratio:.3%}'),
    ]:
        lo, hi = _TECH_ANCHORS[signal]
        pts = round(_scale(raw, lo, hi), 1)
        if pts > 0:
            contributions.append({'signal': signal, 'points': pts, 'note': note})
    return contributions


def _handle_botlike_reasons(handle):
    """Heuristic checks for randomly-generated handles.

    Allows year suffixes (alice1985) and short abbreviations. Flags the
    research-backed patterns: random alpha-numeric strings, long digit runs
    that aren't year-like, long consonant clusters, low vowel ratio in long
    handles. See https://arxiv.org/pdf/1812.05932 for the underlying
    observations on bot username patterns.

    Returns a list of human-readable reasons (empty if handle looks fine).
    """
    if not handle:
        return []
    reasons = []

    # 5+ consecutive digits — beyond a 4-digit year, this looks generated.
    if re.search(r'\d{5,}', handle):
        reasons.append('5+ consecutive digits')
    # 4-digit run followed by more alphanumerics — not a clean year suffix.
    elif re.search(r'\d{4}[A-Za-z]', handle):
        reasons.append('digits embedded mid-handle')

    # 5+ consecutive consonants — real names have vowel structure.
    if re.search(r'[bcdfghjklmnpqrstvwxz]{5,}', handle, re.IGNORECASE):
        reasons.append('5+ consecutive consonants')

    # Long letter run with implausibly low vowel ratio.
    letters = [c for c in handle if c.isalpha()]
    if len(letters) >= 6:
        vowels = sum(1 for c in letters if c.lower() in 'aeiou')
        if vowels / len(letters) < 0.2:
            reasons.append(f'low vowel ratio ({vowels}/{len(letters)})')

    return reasons


def _has_playlists(channel_id):
    """Cheap local check: does this channel have any playlist data we've
    mirrored. Returns False if the playlists subdir doesn't exist or is
    empty. Doesn't trigger any remote fetch."""
    from youtube.playlist import Playlist
    data_dir = Playlist.get_active_dir(channel_id)
    if not data_dir.is_dir():
        return False
    return any(data_dir.glob('*.json'))


def _score_author_channel(channel_id, batch_time):
    """Author-channel scoring. Filters obvious low-effort/farm accounts.

    We don't aim for precision — a downstream cheap-LLM step does the
    finer-grained filtering. The job here is to get the worst out cheaply.
    Returns a list of breakdown entries (positive and negative)."""
    if channel_id is None:
        return []
    chan_file = Channel.get_active_dir(channel_id) / 'channel.json'
    if not chan_file.exists():
        return []
    chan = json.loads(chan_file.read_text())
    breakdown = []

    handle = (chan.get('custom_url') or '').lstrip('@')
    title = (chan.get('title') or '').strip()
    subscribers = int(chan.get('subscriber_count') or 0)
    videos = int(chan.get('uploads_count') or 0)
    published_at = chan.get('published_at')

    has_uploads = videos >= 1
    has_playlists = _has_playlists(channel_id)
    is_active = has_uploads or has_playlists

    botlike_reasons = _handle_botlike_reasons(handle)
    if botlike_reasons:
        # -3 per flag, capped at -10.
        points = max(-10, -3 * len(botlike_reasons))
        breakdown.append({'signal': 'author_handle_botlike', 'points': points,
            'note': f'@{handle}: {"; ".join(botlike_reasons)}'})

    # Low-customization markers (handle == name, default avatar) skip when
    # the channel shows real activity (uploads or curated playlists).
    if not is_active and handle and title and handle.lower() == title.lower():
        breakdown.append({'signal': 'author_handle_eq_name', 'points': -8,
            'note': f'handle and display name both "{title}"'})

    if not is_active:
        thumb_meta_path = (Channel.get_active_dir(channel_id)
                           / 'thumbnails' / 'default.json')
        if thumb_meta_path.exists():
            distinct = json.loads(thumb_meta_path.read_text()).get('distinct_colors')
            if distinct is not None and distinct <= 2:
                breakdown.append({'signal': 'author_no_profile_picture', 'points': -5,
                    'note': f'default-letter avatar ({distinct} distinct colors)'})

    if published_at:
        try:
            published_dt = datetime.fromisoformat(published_at)
        except ValueError:
            published_dt = None
        if published_dt:
            age_days = (batch_time - published_dt).days
            if age_days >= 5 * 365:
                breakdown.append({'signal': 'author_age_5y+', 'points': 3,
                    'note': f'channel ~{age_days // 365}y old'})

    if subscribers >= 20:
        breakdown.append({'signal': 'author_subs_20+', 'points': 3,
            'note': f'{subscribers} subscribers'})

    if is_active:
        note_parts = []
        if has_uploads:
            note_parts.append(f'{videos} uploads')
        if has_playlists:
            note_parts.append('has playlists')
        breakdown.append({'signal': 'author_active_channel', 'points': 2,
            'note': '; '.join(note_parts)})

    return breakdown


def author_tier(channel_id, creator_id):
    if channel_id is None:
        return 'unknown'
    if channel_id == creator_id:
        return 'creator'
    if (Subscription.data_dir() / f'{channel_id}.json').exists():
        return 'subscribed'
    if (Channel.get_active_dir(channel_id) / 'channel.json').exists():
        return 'known'
    return 'unknown'


def load_chapters(video):
    headings_file = Video.get_processed_dir(video.video_id) / 'headings.txt'
    if not headings_file.exists():
        return []
    chapters = []
    for line in headings_file.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(' ', 1)
        if len(parts) != 2:
            continue
        offset_str, rest = parts
        if not offset_str.isdigit():
            continue
        title = rest.lstrip('#').strip()
        chapters.append((int(offset_str), title))
    return chapters


def chapter_for_offset(chapters, offset_seconds):
    if not chapters:
        return None
    if offset_seconds < chapters[0][0]:
        return None
    for i, (start, _) in enumerate(chapters):
        next_start = chapters[i + 1][0] if i + 1 < len(chapters) else float('inf')
        if start <= offset_seconds < next_start:
            return i
    return None


def _is_anti(text, features, like_count):
    # All-caps shouting, with non-trivial length.
    if features['caps_ratio'] > 0.5 and features['length'] > 10:
        return True
    # Emoji-saturated content.
    if features['emoji_density'] > 0.2:
        return True
    # Stripped of URLs/whitespace, the comment is empty (URL-only spam).
    stripped = text_features._URL_RE.sub('', text).strip()
    if not stripped and text:
        return True
    return False


def _passes_gate(features, referent_ents, has_citation, tier):
    if tier in ('subscribed', 'creator'):
        return True
    if features['length'] >= MIN_QUALITY_LEN:
        return True
    if referent_ents:
        return True
    if has_citation:
        return True
    return False


def _classify_comment(comment, ctx):
    text = comment['text_original'] or ''
    features = text_features.structural_features(text)
    tier = author_tier(comment.get('author_channel_id'), ctx['creator_id'])

    if _is_anti(text, features, comment.get('like_count', 0)):
        return {
            'quality_class': 'anti',
            'score': 0,
            'tags': {
                'author_tier': tier,
                'entities': [],
                'chapter_indices': [],
                'breakdown': [{'signal': 'anti', 'points': 0}],
            },
            'parent_id': comment.get('parent_id'),
        }

    # NER and chapter mapping aren't free; only run them when worth it.
    needs_ner = features['length'] >= 30 or tier in ('creator', 'subscribed')
    ents = text_features.entities(text) if needs_ner else []
    referent_ents = [e for e in ents if e[0] in _REFERENT_LABELS]

    # Chapters are tagged for downstream topic-of-comment work, not for
    # scoring. A chapter timestamp by itself doesn't make a comment substantive.
    timestamps = text_features.extract_timestamps(text)
    chapter_indices = []
    for offset, _ in timestamps:
        idx = chapter_for_offset(ctx['chapters'], offset)
        if idx is not None and idx not in chapter_indices:
            chapter_indices.append(idx)

    has_citation = text_features.has_citation_marker(text)
    passes_gate = _passes_gate(features, referent_ents, has_citation, tier)

    breakdown = []

    # Creator's own comments don't get a tier bonus — they're scored on
    # their content like any other comment. The signal of "this comment
    # mattered to the creator" goes on the *parent* (see below).

    if tier == 'subscribed':
        breakdown.append({'signal': 'subscribed', 'points': 100})

    if has_citation:
        breakdown.append({'signal': 'citation_marker', 'points': 5})

    effort_pts = _effort_band_points(features['length'])
    if effort_pts != 0:
        breakdown.append({'signal': 'effort_band', 'points': effort_pts,
            'note': f'length {features["length"]}'})

    if features['sentence_count'] >= 2:
        # 0.5 per sentence, capped at 5. Long ramble shouldn't outscore a
        # tight, well-structured short essay.
        pts = min(5, 0.5 * features['sentence_count'])
        breakdown.append({'signal': 'sentence_count', 'points': pts,
            'note': f'{features["sentence_count"]} sentences'})

    breakdown.extend(_technicality_contributions(text, features['sentence_count']))

    # Mid-sentence Title-Case ratio: name-dropping concept-labels.
    # Stepped: 2% → +1, 3% → +2, ..., 6%+ → +5 (capped).
    caps_pct = int(features['mid_sentence_caps_ratio'] * 100)
    if caps_pct >= 2:
        breakdown.append({'signal': 'tech_mid_sentence_caps',
            'points': min(5, caps_pct - 1),
            'note': f'{features["mid_sentence_caps_ratio"]:.2%} mid-sentence Title-Case'})

    # Engagement: split into separate rows so each contribution is visible.
    cid = comment.get('comment_id')
    total_replies = comment.get('total_reply_count', 0) or 0
    if total_replies >= 1:
        breakdown.append({'signal': 'engagement_replies', 'points': 2,
            'note': f'{total_replies} replies'})
    if cid in ctx['at_mention_parent_ids']:
        breakdown.append({'signal': 'engagement_reply_to_reply', 'points': 2,
            'note': 'reply chain (@-mention)'})
    likes = comment.get('like_count', 0) or 0
    if likes > 0:
        breakdown.append({'signal': 'engagement_likes', 'points': 1,
            'note': f'{likes} likes'})

    posted_at = comment.get('published_at')
    edited_at = comment.get('updated_at')
    if posted_at and edited_at and posted_at != edited_at:
        breakdown.append({'signal': 'edited', 'points': 1,
            'note': f'last edited {edited_at}'})

    # Creator engagement on the parent: replied / liked / reply length tiers.
    # Each contributes +1, sums to at most 5 by construction (5 conditions).
    creator_reply_len = ctx['creator_reply_lengths'].get(cid, 0)
    if creator_reply_len > 0:
        breakdown.append({'signal': 'creator_replied', 'points': 1,
            'note': f"creator's reply is {creator_reply_len} chars"})
    if _creator_liked_comment(comment, ctx):
        breakdown.append({'signal': 'creator_liked', 'points': 1,
            'note': 'creator hearted this comment'})
    if creator_reply_len > 200:
        breakdown.append({'signal': 'creator_reply_>200', 'points': 1,
            'note': "creator's reply > 200 chars"})
    if creator_reply_len > 400:
        breakdown.append({'signal': 'creator_reply_>400', 'points': 1,
            'note': "creator's reply > 400 chars"})
    if creator_reply_len > 600:
        breakdown.append({'signal': 'creator_reply_>600', 'points': 1,
            'note': "creator's reply > 600 chars"})

    entry = ctx['relevance_points'].get(comment.get('comment_id'))
    if entry:
        pts, note = entry
        breakdown.append({'signal': 'youtube_relevance_top', 'points': pts,
            'note': note})

    breakdown.extend(_score_author_channel(
        comment.get('author_channel_id'),
        ctx['batch_time'],
    ))

    score = round(sum(b['points'] for b in breakdown), 1)

    if not passes_gate:
        klass = 'ignorable'
    elif score >= QUALITY_SCORE_THRESHOLD:
        klass = 'quality'
    else:
        klass = 'ignorable'

    return {
        'quality_class': klass,
        'score': score,
        'tags': {
            'author_tier': tier,
            'entities': ents,
            'chapter_indices': chapter_indices,
            'breakdown': breakdown,
        },
        'parent_id': comment.get('parent_id'),
    }


EXPAND_SCORE_THRESHOLD = 10
RELEVANCE_MAX_POINTS = 6


def _expand_quality_threads(video, results, comments_dict):
    """Expand replies for top-level comments scored at or above
    EXPAND_SCORE_THRESHOLD (and have unfetched replies).

    Returns the list of comment_ids whose threads were expanded — those
    need re-classification because the engagement signal (reply-to-reply
    @-mentions) depends on the full reply set."""
    expanded = []
    for cid, result in list(results.items()):
        if result['parent_id'] is not None:
            continue
        if result['score'] < EXPAND_SCORE_THRESHOLD:
            continue
        comment = comments_dict.get(cid)
        if not comment:
            continue
        if comment.get('replies_complete'):
            continue
        total = comment.get('total_reply_count', 0) or 0
        inline_count = sum(
            1 for c in comments_dict.values() if c.get('parent_id') == cid
        )
        if total <= inline_count:
            continue
        video.expand_replies(cid)
        expanded.append(cid)
    return expanded


def _creator_liked_comment(comment, ctx):
    """Did the video creator heart/like this comment.

    TODO(creator-heart): the YouTube Data API doesn't currently expose
    creator hearts (the heart icon under a comment). When/if available
    via the API or a scraping fallback, populate this. Until then it
    always returns False — the signal is wired into scoring so that
    flipping this on later doesn't require breakdown surgery."""
    return False


def _passes_cheap_text_gate(comment, ctx):
    """Cheap text-only filter for 'worth fetching the author's channel data'.
    Avoids triggering channel/thumbnail fetches for obvious junk comments.
    Conservative — false positives waste a CDN fetch, false negatives miss
    a useful channel signal."""
    text = comment.get('text_original') or ''
    if not text:
        return False
    cid = comment.get('author_channel_id')
    if cid == ctx['creator_id']:
        return False
    if cid is None:
        return False
    if (Subscription.data_dir() / f'{cid}.json').exists():
        return False
    if len(text) >= 50:
        return True
    return False


def _trigger_author_fetch(comment, ctx):
    cid = comment.get('author_channel_id')
    if not cid:
        return
    if cid == ctx['creator_id']:
        return
    if (Subscription.data_dir() / f'{cid}.json').exists():
        return
    chan = Channel.get(cid)  # idempotent — only fetches if channel.json missing
    chan.fetch_default_thumbnail_features()  # idempotent — only fetches if default.json missing


def classify(video, expand=True, fetch_authors=True, force=False):
    out_file = Video.get_processed_dir(video.video_id) / 'comments_classified.json'
    if not force and out_file.exists():
        cached = json.loads(out_file.read_text())
        if cached.get('schema_version') == SCHEMA_VERSION:
            return cached['classifications']

    chapters = load_chapters(video)
    creator_id = video.channel_id
    batch_time = Context.get().batch_time

    comments_file = Video.get_active_comments_file(video.video_id)
    if not comments_file.exists():
        video.mirror_comments()
    if not comments_file.exists():
        comments_dict = {}
    else:
        comments_dict = json.loads(comments_file.read_text()).get('comments', {})

    # YouTube returns commentThreads in 'relevance' order on the first fetch.
    # Linear bump for early-returned top-level comments: rank 0 (most
    # relevant) gets RELEVANCE_MAX_POINTS, falling off to 0 at the cutoff
    # (top third). Smoother than discrete tiers and self-scaling to video size.
    top_level_ids = [cid for cid, c in comments_dict.items() if c.get('parent_id') is None]
    n = len(top_level_ids)
    cutoff = max(1, n // 3) if n else 0
    relevance_points = {}
    for i, cid in enumerate(top_level_ids[:cutoff]):
        pts = round(RELEVANCE_MAX_POINTS * (1 - i / cutoff), 1)
        if pts > 0:
            relevance_points[cid] = (pts, f'rank {i + 1}/{n}')

    # Top-level comments whose threads contain reply-to-reply (@-mention prefix).
    # YouTube's UI prepends @<author> when you reply to a reply; the prefix can
    # include zero-width spaces or BOM-style invisibles. Strip those too.
    at_mention_re = re.compile(r'^[\s​‌‍﻿]*@')
    at_mention_parent_ids = {
        c['parent_id'] for c in comments_dict.values()
        if c.get('parent_id') and at_mention_re.match(c.get('text_original') or '')
    }

    # Top-level comments to which the video creator replied. Length of the
    # creator's reply is a proxy for "did they engage substantively or just
    # acknowledge". Stored as {parent_id: max_creator_reply_length}.
    creator_reply_lengths = {}
    for c in comments_dict.values():
        if c.get('parent_id') and c.get('author_channel_id') == creator_id:
            pid = c['parent_id']
            length = len(c.get('text_original') or '')
            if length > creator_reply_lengths.get(pid, 0):
                creator_reply_lengths[pid] = length

    ctx = {
        'chapters': chapters,
        'creator_id': creator_id,
        'batch_time': batch_time,
        'relevance_points': relevance_points,
        'at_mention_parent_ids': at_mention_parent_ids,
        'creator_reply_lengths': creator_reply_lengths,
    }

    def _prefetch_and_classify(cid, comment):
        # Two-stage: (1) cheap text-feature classify to decide if it's worth
        # fetching the author's channel + thumbnail; (2) if so, prefetch and
        # re-classify with the channel signals available.
        if fetch_authors and _passes_cheap_text_gate(comment, ctx):
            _trigger_author_fetch(comment, ctx)
        results[cid] = _classify_comment(comment, ctx)

    results = {}
    for cid, comment in comments_dict.items():
        _prefetch_and_classify(cid, comment)

    if expand:
        expanded_ids = _expand_quality_threads(video, results, comments_dict)
        if expanded_ids:
            comments_dict = json.loads(comments_file.read_text()).get('comments', {})
            # Newly-fetched replies may complete @-mention chains; refresh.
            ctx['at_mention_parent_ids'] = {
                c['parent_id'] for c in comments_dict.values()
                if c.get('parent_id') and (c.get('text_original') or '').lstrip().startswith('@')
            }
            # Re-classify expanded top-level comments — their engagement
            # score depends on the now-complete reply set.
            for cid in expanded_ids:
                _prefetch_and_classify(cid, comments_dict[cid])
            # Classify any newly-arrived replies.
            for cid, comment in comments_dict.items():
                if cid in results:
                    continue
                _prefetch_and_classify(cid, comment)

    dump_json(out_file, {
        'schema_version': SCHEMA_VERSION,
        'video_id': video.video_id,
        'classified_at': Context.get().batch_time.isoformat(),
        'classifications': results,
    })

    return results
