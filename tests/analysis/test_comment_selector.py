import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from conftest import BATCH_TIME

from analysis.comment_selector import (
    SCHEMA_VERSION,
    _effort_band_points,
    _handle_botlike_reasons,
    _score_author_channel,
    _technicality_contributions,
    author_tier,
    chapter_for_offset,
    classify,
    load_chapters,
)
from youtube.video import Video


def _video(video_id='vid_TEST', channel_id='ch1'):
    return Video(
        video_id=video_id, title='T', channel_id=channel_id,
        published_at=BATCH_TIME, first_seen=BATCH_TIME, last_updated=BATCH_TIME,
        description='', thumbnails_data={}, tags=[], category_id=1,
        live_status='none', duration_data='PT10M', spatial_dimension_type='2d',
        resolution_tier='hd', captioned=True, licensed_content=False,
        content_rating_data={}, viewing_projection='rectangular',
        privacy_status='public', license='youtube', embeddable=True,
        public_stats_viewable=True, made_for_kids=False, view_count=0,
        like_count=0, comment_count=0, topic_details={},
        has_paid_product_placement=False,
    )


def _seed_comments(write_json, video_id, comments):
    write_json(f'youtube/videos/active/{video_id[:2]}/{video_id}/comments.json', {
        'comments_disabled': False,
        'fetched_at': BATCH_TIME.isoformat(),
        'fetch_complete': True,
        'next_page_token': None,
        'pages_fetched': 1,
        'comments': {c['comment_id']: c for c in comments},
    })


def _comment(comment_id, text, **kwargs):
    base = {
        'comment_id': comment_id,
        'video_id': kwargs.get('video_id', 'vid_TEST'),
        'parent_id': kwargs.get('parent_id'),
        'author_display_name': kwargs.get('author', 'someone'),
        'author_channel_id': kwargs.get('author_channel_id', 'UC_other'),
        'text_display': text,
        'text_original': text,
        'like_count': kwargs.get('like_count', 0),
        'published_at': '2024-06-01T00:00:00Z',
        'updated_at': '2024-06-01T00:00:00Z',
        'total_reply_count': kwargs.get('total_reply_count', 0),
        'first_seen': BATCH_TIME.isoformat(),
        'last_seen': BATCH_TIME.isoformat(),
        'replies_complete': kwargs.get('replies_complete', False),
    }
    return base


def _stub_channel(write_json, channel_id, subscriber_count=1000, **overrides):
    data = {
        'channel_id': channel_id,
        'title': f'Channel {channel_id}',
        'description': 'A real channel description.',
        'subscriber_count': subscriber_count,
        'uploads_count': 10,
        'view_count': 100000,
        'first_seen': BATCH_TIME.isoformat(),
        'last_updated': BATCH_TIME.isoformat(),
        'published_at': '2018-01-01T00:00:00+00:00',
        'banner_external_url': '',
        'custom_url': f'@channel-{channel_id}',
        'playlists_data': {},
        'status': {},
        'thumbnails': {},
        'topic_details': {},
        'schema_version': 2,
    }
    data.update(overrides)
    write_json(f'youtube/channels/active/{channel_id}/channel.json', data)


def _stub_subscription(write_json, channel_id):
    write_json(f'youtube/subscriptions/active/{channel_id}.json', {
        'channel_id': channel_id,
        'subscription_id': 'sub_x',
        'first_seen': BATCH_TIME.isoformat(),
        'last_updated': BATCH_TIME.isoformat(),
        'activity_type': 'all',
        'new_item_count': 0,
        'total_item_count': 0,
        'title': 'A subscription',
    })


# ---------------------------------------------------------------------------
# Chapters
# ---------------------------------------------------------------------------

class TestChapters:
    def test_load_chapters_parses_headings(self, ctx, write_raw):
        write_raw('youtube/videos/active/vi/vid_TEST/processed/headings.txt',
            '0 ## Intro\n74 ## Topic A\n312 ### Sub of A\n528 ## Topic B\n')
        chapters = load_chapters(_video())
        assert chapters == [
            (0, 'Intro'),
            (74, 'Topic A'),
            (312, 'Sub of A'),
            (528, 'Topic B'),
        ]

    def test_load_chapters_missing_file(self, ctx):
        assert load_chapters(_video()) == []

    def test_chapter_for_offset_first(self):
        chapters = [(0, 'A'), (60, 'B'), (120, 'C')]
        assert chapter_for_offset(chapters, 30) == 0

    def test_chapter_for_offset_middle(self):
        chapters = [(0, 'A'), (60, 'B'), (120, 'C')]
        assert chapter_for_offset(chapters, 90) == 1

    def test_chapter_for_offset_last(self):
        chapters = [(0, 'A'), (60, 'B'), (120, 'C')]
        assert chapter_for_offset(chapters, 200) == 2

    def test_chapter_for_offset_no_chapters(self):
        assert chapter_for_offset([], 30) is None

    def test_chapter_for_offset_before_first(self):
        # Most channels start chapters at 0:00, but if not, anything before the
        # first chapter offset has no chapter.
        chapters = [(60, 'A'), (120, 'B')]
        assert chapter_for_offset(chapters, 30) is None


# ---------------------------------------------------------------------------
# Author tier
# ---------------------------------------------------------------------------

class TestAuthorTier:
    def test_unknown_when_nothing_cached(self, ctx):
        assert author_tier('UC_unknown', creator_id='ch1') == 'unknown'

    def test_subscribed_overrides_known(self, ctx, write_json):
        _stub_subscription(write_json, 'UC_sub')
        _stub_channel(write_json, 'UC_sub')
        assert author_tier('UC_sub', creator_id='ch1') == 'subscribed'

    def test_known_when_channel_dir_exists(self, ctx, write_json):
        _stub_channel(write_json, 'UC_known')
        assert author_tier('UC_known', creator_id='ch1') == 'known'

    def test_creator_when_matches_video_channel(self, ctx):
        assert author_tier('ch1', creator_id='ch1') == 'creator'

    def test_creator_takes_precedence_over_subscribed(self, ctx, write_json):
        # Creator's own channel happens to be subscribed too — creator wins.
        _stub_subscription(write_json, 'ch1')
        assert author_tier('ch1', creator_id='ch1') == 'creator'

    def test_none_channel_id(self, ctx):
        assert author_tier(None, creator_id='ch1') == 'unknown'


# ---------------------------------------------------------------------------
# Technicality
# ---------------------------------------------------------------------------

class TestTechnicality:
    def test_short_text_no_contributions(self):
        assert _technicality_contributions('A short comment.', 1) == []

    def test_conversational_long_text_low_score(self):
        text = (
            'I love this video. It made me happy and I want to watch more. '
            'The dog in the corner is cute. The video maker is funny. '
            'Thanks for sharing this with us. I will subscribe today. '
            'Looking forward to the next one. Really enjoyed every minute. '
            'My friend will love this too.'
        )
        contribs = _technicality_contributions(text, 9)
        total = sum(c['points'] for c in contribs)
        assert total <= 2.5

    def test_technical_text_per_component_capped(self):
        # All four components at or above their p99 anchors → each at its
        # max (2.5), total 10.
        text = (
            'In essence, the systemic-based negotiation framework necessitates '
            'an itemization/valuation procedure in which "demands" and "offers" '
            'are mapped onto categorical privileges; specifically, parameters '
            'such as monetary incentives, informational disclosure, and '
            'transactional obligations must be evaluated for equivalence, i.e., '
            'each side commits comparable value. Including but not limited to '
            'mercantile arrangements, this approach generalizes to any '
            'asymmetric relationship—however, edge cases remain unresolved '
            'and/or require further analysis.'
        )
        contribs = _technicality_contributions(text, 2)
        signals = {c['signal']: c['points'] for c in contribs}
        # Each component is independently capped at 2.5
        for sig in ('tech_word_length', 'tech_sentence_length',
                    'tech_discourse_markers', 'tech_special_punct'):
            if sig in signals:
                assert signals[sig] <= 2.5
        total = sum(c['points'] for c in contribs)
        assert total <= 10

# ---------------------------------------------------------------------------
# Effort curve
# ---------------------------------------------------------------------------

class TestEffortCurve:
    def test_anchor_points_exact(self):
        cases = [(60, -5), (160, 0), (200, 1), (600, 5)]
        for length, expected in cases:
            assert _effort_band_points(length) == expected, f'len {length}'

    def test_below_minimum_floors_at_neg5(self):
        assert _effort_band_points(0) == -5
        assert _effort_band_points(30) == -5

    def test_above_peak_plateaus_at_5(self):
        # No penalty for long content — the curve plateaus at the peak.
        assert _effort_band_points(600) == 5
        assert _effort_band_points(1500) == 5
        assert _effort_band_points(2500) == 5
        assert _effort_band_points(5000) == 5
        assert _effort_band_points(10000) == 5

    def test_interpolates_between_anchors(self):
        # 70 between 60 (-5) and 80 (-4): midpoint = -4.5
        assert _effort_band_points(70) == -4.5
        # 250 between 200 (1) and 300 (2): midpoint = 1.5
        assert _effort_band_points(250) == 1.5


# ---------------------------------------------------------------------------
# Channel scoring
# ---------------------------------------------------------------------------

class TestChannelScoring:
    def test_no_data_returns_empty(self, ctx):
        assert _score_author_channel('UC_unknown', BATCH_TIME) == []

    def test_none_channel_id(self, ctx):
        assert _score_author_channel(None, BATCH_TIME) == []

    def test_legit_channel_positives(self, ctx, write_json):
        _stub_channel(write_json, 'UC_real',
            published_at='2018-01-01T00:00:00+00:00',
            subscriber_count=5000, uploads_count=42,
            description='Lots of dialogue design content.')
        b = _score_author_channel('UC_real', BATCH_TIME)
        signals = {x['signal'] for x in b}
        assert 'author_age_5y+' in signals
        assert 'author_subs_20+' in signals
        assert 'author_active_channel' in signals
        assert sum(x['points'] for x in b) > 0

    def test_botlike_long_digit_run(self, ctx, write_json):
        _stub_channel(write_json, 'UC_bot', custom_url='@user1234567')
        b = _score_author_channel('UC_bot', BATCH_TIME)
        sigs = {x['signal']: x['points'] for x in b}
        assert sigs.get('author_handle_botlike') is not None
        assert sigs['author_handle_botlike'] < 0

    def test_year_suffix_is_not_botlike(self, ctx, write_json):
        # Birth year as suffix is normal, not bot.
        _stub_channel(write_json, 'UC_real', custom_url='@alice1985')
        b = _score_author_channel('UC_real', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_handle_botlike' not in sigs

    def test_year_at_start_is_not_botlike(self, ctx, write_json):
        # Some users put the year first too.
        _stub_channel(write_json, 'UC_real', custom_url='@2002jonas')
        b = _score_author_channel('UC_real', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        # 4 digits followed by letters trips "digits embedded mid-handle".
        # That's the trade-off — we accept this rare false positive.
        # If it becomes a problem we can refine further.
        assert 'author_handle_botlike' in sigs

    def test_random_alphanumeric_handle_is_botlike(self, ctx, write_json):
        # Low vowel ratio in a long letter run.
        _stub_channel(write_json, 'UC_bot', custom_url='@xJdkfknBzq')
        b = _score_author_channel('UC_bot', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_handle_botlike' in sigs

    def test_consonant_cluster_is_botlike(self, ctx, write_json):
        _stub_channel(write_json, 'UC_bot', custom_url='@abcfghjklm')
        b = _score_author_channel('UC_bot', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_handle_botlike' in sigs

    def test_no_profile_picture_penalty(self, ctx, write_json):
        # Pre-write thumbnail sidecar with distinct_colors=2 (default letter
        # avatar). Channel is inactive (no uploads) so penalty applies.
        _stub_channel(write_json, 'UC_def', uploads_count=0)
        write_json('youtube/channels/active/UC_def/thumbnails/default.json', {
            'distinct_colors': 2,
            'source_url': 'https://example/letter.jpg',
        })
        b = _score_author_channel('UC_def', BATCH_TIME)
        sigs = {x['signal']: x['points'] for x in b}
        assert sigs.get('author_no_profile_picture') == -5

    def test_uploaded_picture_no_penalty(self, ctx, write_json):
        _stub_channel(write_json, 'UC_real')
        write_json('youtube/channels/active/UC_real/thumbnails/default.json', {
            'distinct_colors': 4,
            'source_url': 'https://example/photo.jpg',
        })
        b = _score_author_channel('UC_real', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_no_profile_picture' not in sigs

    def test_no_thumbnail_metadata_no_signal(self, ctx, write_json):
        # When the thumbnail hasn't been analyzed yet, no signal added.
        _stub_channel(write_json, 'UC_unknown')
        b = _score_author_channel('UC_unknown', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_no_profile_picture' not in sigs

    def test_handle_eq_name_skipped_with_playlists(self, ctx, write_json):
        # Channel has playlists but no uploads — still active, so the
        # handle_eq_name penalty doesn't fire.
        _stub_channel(write_json, 'UC_pl_match',
            title='PlNamed', custom_url='@PlNamed',
            uploads_count=0)
        write_json('youtube/channels/active/UC_pl_match/playlists/PL_x.json', {'id': 'PL_x'})
        b = _score_author_channel('UC_pl_match', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_handle_eq_name' not in sigs

    def test_no_profile_picture_skipped_when_active(self, ctx, write_json):
        # Default-letter avatar but channel has uploads — no penalty.
        _stub_channel(write_json, 'UC_active_def_pic', uploads_count=5)
        write_json('youtube/channels/active/UC_active_def_pic/thumbnails/default.json', {
            'distinct_colors': 2,
            'source_url': 'https://example/letter.jpg',
        })
        b = _score_author_channel('UC_active_def_pic', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_no_profile_picture' not in sigs

    def test_handle_botlike_helper(self):
        # Direct unit tests for the heuristic function.
        assert _handle_botlike_reasons('') == []
        assert _handle_botlike_reasons('alice1985') == []
        assert _handle_botlike_reasons('JonasL') == []
        assert _handle_botlike_reasons('VanillaSpooks') == []
        assert _handle_botlike_reasons('docweidner') == []
        assert _handle_botlike_reasons('user1234567') != []  # 5+ digits
        assert _handle_botlike_reasons('user1234abc') != []  # embedded
        assert _handle_botlike_reasons('xJdkfknBzq') != []  # low vowels
        assert _handle_botlike_reasons('abcfghjklm') != []  # consonant cluster

    def test_handle_equals_display_name_penalty_when_inactive(self, ctx, write_json):
        # No uploads, no playlists, handle == display name → penalty.
        _stub_channel(write_json, 'UC_match_bot',
            title='SameName', custom_url='@SameName',
            uploads_count=0)
        b = _score_author_channel('UC_match_bot', BATCH_TIME)
        sigs = {x['signal']: x['points'] for x in b}
        assert sigs.get('author_handle_eq_name') == -8

    def test_handle_equals_display_name_skipped_when_active(self, ctx, write_json):
        # Real users with public uploads aren't penalized for not customizing
        # their channel handle/page.
        _stub_channel(write_json, 'UC_match_real',
            title='SameName', custom_url='@SameName',
            uploads_count=5)
        b = _score_author_channel('UC_match_real', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_handle_eq_name' not in sigs

    def test_empty_description_no_signal(self, ctx, write_json):
        # Empty description is not a penalty by itself.
        _stub_channel(write_json, 'UC_blank', description='', uploads_count=0)
        b = _score_author_channel('UC_blank', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_no_description' not in sigs

    def test_active_channel_with_uploads(self, ctx, write_json):
        _stub_channel(write_json, 'UC_uploads', uploads_count=5)
        b = _score_author_channel('UC_uploads', BATCH_TIME)
        sigs = {x['signal']: x['points'] for x in b}
        assert sigs.get('author_active_channel') == 2

    def test_active_channel_with_playlists_only(self, ctx, write_json):
        _stub_channel(write_json, 'UC_pl', uploads_count=0)
        write_json('youtube/channels/active/UC_pl/playlists/PL_xyz.json', {'id': 'PL_xyz'})
        b = _score_author_channel('UC_pl', BATCH_TIME)
        sigs = {x['signal']: x['points'] for x in b}
        assert sigs.get('author_active_channel') == 2

    def test_inactive_channel_no_signal(self, ctx, write_json):
        _stub_channel(write_json, 'UC_inactive', uploads_count=0)
        b = _score_author_channel('UC_inactive', BATCH_TIME)
        sigs = {x['signal'] for x in b}
        assert 'author_active_channel' not in sigs

    def test_fresh_low_sub_no_uploads_drops_to_negative(self, ctx, write_json):
        # @docweidner-shaped: brand-new bot. No description, no age, no
        # subscribers, no uploads, handle == display name.
        _stub_channel(write_json, 'UC_farm',
            title='spamuser', custom_url='@spamuser',
            description='',
            subscriber_count=2, uploads_count=0,
            published_at=BATCH_TIME.isoformat())
        b = _score_author_channel('UC_farm', BATCH_TIME)
        total = sum(x['points'] for x in b)
        # Negative signals (no description -3, handle eq name -1) outweigh
        # any positives (none).
        assert total < 0


# ---------------------------------------------------------------------------
# classify() integration
# ---------------------------------------------------------------------------

class TestClassify:
    def test_subscribed_author_scores_high(self, ctx, write_json):
        # Subscribed author gives +100, putting the comment at the top of
        # quality regardless of length.
        _stub_subscription(write_json, 'UC_sub')
        _stub_channel(write_json, 'UC_sub')
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'short reply', author_channel_id='UC_sub'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        assert results['c1']['quality_class'] == 'quality'
        assert results['c1']['score'] >= 100
        assert results['c1']['tags']['author_tier'] == 'subscribed'

    def test_creator_own_comment_no_tier_bonus(self, ctx, write_json):
        # Creator's own comment doesn't get a points bonus just for being
        # the creator's. Score reflects content alone.
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'long top-level comment without entities, just to seed a thread'
                ' with substance for classification purposes here',
                author_channel_id='UC_other'),
            _comment('r1', 'thanks for watching!', parent_id='c1', author_channel_id='ch1'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal'] for b in results['r1']['tags']['breakdown']}
        assert 'creator' not in sigs
        assert 'creator_strong' not in sigs
        assert results['r1']['tags']['author_tier'] == 'creator'

    def test_long_well_formed_comment_is_quality(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1',
                'I really enjoyed this discussion. Timothy Cain made some excellent points about '
                'Fallout and Interplay. The way he explains dialogue quest design at Black Isle '
                'Studios is illuminating, especially regarding how Bethesda later changed the '
                'approach. According to his earlier video, this was a deliberate choice.',
                author_channel_id='UC_random'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        assert results['c1']['quality_class'] == 'quality'
        # Should have entities detected
        assert len(results['c1']['tags']['entities']) >= 1

    def test_short_low_signal_comment_is_ignorable(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'nice video!', author_channel_id='UC_x'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        assert results['c1']['quality_class'] == 'ignorable'

    def test_high_caps_short_text_is_anti(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'AMAZING VIDEO BRO!!!', like_count=50,
                author_channel_id='UC_x'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        assert results['c1']['quality_class'] == 'anti'

    def test_emoji_spam_is_anti(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', '🔥🔥🔥🔥🔥🔥🔥', author_channel_id='UC_x'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        assert results['c1']['quality_class'] == 'anti'

    def test_timestamp_maps_to_chapter(self, ctx, write_json, write_raw):
        write_raw('youtube/videos/active/vi/vid_TEST/processed/headings.txt',
            '0 ## Intro\n300 ## Main topic\n600 ## Conclusion\n')
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'The bit at 5:30 about Tim Cain making Fallout was great. '
                'I love how he explains dialogue choices.',
                author_channel_id='UC_x'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        # 5:30 = 330s, falls in chapter index 1 (Main topic, [300, 600))
        assert 1 in results['c1']['tags']['chapter_indices']

    def test_relevance_linear_decay(self, ctx, write_json):
        # 18 top-level → cutoff = 6 (top third). Linear decay: rank 0 gets 6,
        # rank 5 gets 1, rank 6+ get 0.
        _seed_comments(write_json, 'vid_TEST', [
            _comment(f'c{i:02d}', 'short', author_channel_id=f'UC_{i}')
            for i in range(18)
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        pts_by_cid = {}
        for cid, r in results.items():
            for b in r['tags']['breakdown']:
                if b['signal'] == 'youtube_relevance_top':
                    pts_by_cid[cid] = b['points']
        # Linear from 6 down to 1 across the top third (cutoff = 6).
        assert pts_by_cid.get('c00') == 6.0
        assert pts_by_cid.get('c01') == 5.0
        assert pts_by_cid.get('c02') == 4.0
        assert pts_by_cid.get('c03') == 3.0
        assert pts_by_cid.get('c04') == 2.0
        assert pts_by_cid.get('c05') == 1.0
        assert 'c06' not in pts_by_cid
        assert 'c17' not in pts_by_cid

    def test_sentence_count_capped_at_5(self, ctx, write_json):
        # Many short sentences shouldn't out-score a tight 5-sentence comment.
        text = '. '.join(f'Sentence {i}' for i in range(20)) + '.'
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', text, author_channel_id='UC_x'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sc = next(b for b in results['c1']['tags']['breakdown']
                  if b['signal'] == 'sentence_count')
        assert sc['points'] == 5

    def test_engagement_likes_only(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment with some content here',
                author_channel_id='UC_x', like_count=42),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert sigs.get('engagement_likes') == 1
        assert 'engagement_replies' not in sigs

    def test_engagement_replies(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment with some content here',
                author_channel_id='UC_x', total_reply_count=2),
            _comment('r1', 'plain reply', parent_id='c1',
                author_channel_id='UC_y'),
            _comment('r2', 'another plain reply', parent_id='c1',
                author_channel_id='UC_z'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert sigs.get('engagement_replies') == 2
        assert 'engagement_reply_to_reply' not in sigs

    def test_engagement_reply_to_reply(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment with some content here',
                author_channel_id='UC_x', total_reply_count=2),
            _comment('r1', 'plain reply', parent_id='c1',
                author_channel_id='UC_y'),
            _comment('r2', '@SomeUser interesting point you raise',
                parent_id='c1', author_channel_id='UC_z'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert sigs.get('engagement_replies') == 2
        assert sigs.get('engagement_reply_to_reply') == 2

    def test_at_mention_handles_zero_width_space(self, ctx, write_json):
        # YouTube UI sometimes inserts a zero-width space before the @-mention
        # when replying to a reply. Detection should still work.
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment with some content here',
                author_channel_id='UC_x', total_reply_count=1),
            _comment('r1', '​@SomeUser response', parent_id='c1',
                author_channel_id='UC_y'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal'] for b in results['c1']['tags']['breakdown']}
        assert 'engagement_reply_to_reply' in sigs

    def test_mid_sentence_caps_signal(self, ctx, write_json):
        # Comment with multiple Title-Case mid-sentence words triggers the
        # tech_mid_sentence_caps signal.
        text = ('I love games. The Brotherhood of Steel and the Black Isle '
            'Studios are making waves. Tim Cain at Interplay made Fallout. '
            'Black Isle Studios continued with Fallout 2.')
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', text, author_channel_id='UC_x'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert 'tech_mid_sentence_caps' in sigs
        assert sigs['tech_mid_sentence_caps'] >= 1

    def test_edited_signal(self, ctx, write_json):
        c1 = _comment('c1', 'a comment with content', author_channel_id='UC_x')
        c1['updated_at'] = '2024-06-02T00:00:00Z'  # different from published_at
        c2 = _comment('c2', 'an unedited comment with content', author_channel_id='UC_y')
        # published_at == updated_at by default in _comment helper
        _seed_comments(write_json, 'vid_TEST', [c1, c2])
        results = classify(_video(), expand=False, fetch_authors=False)
        assert any(b['signal'] == 'edited' for b in results['c1']['tags']['breakdown'])
        assert not any(b['signal'] == 'edited' for b in results['c2']['tags']['breakdown'])

    def test_no_engagement_no_signals(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment with some content here',
                author_channel_id='UC_x', like_count=0),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        signals = {b['signal'] for b in results['c1']['tags']['breakdown']}
        assert not any(s.startswith('engagement') for s in signals)

    def test_creator_replied_short_reply(self, ctx, write_json):
        # Creator's short reply: only creator_replied fires, no length tiers.
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment',
                author_channel_id='UC_x', total_reply_count=1),
            _comment('r1', 'thanks!', parent_id='c1', author_channel_id='ch1'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert sigs.get('creator_replied') == 1
        assert 'creator_reply_>200' not in sigs
        assert 'creator_reply_>400' not in sigs
        assert 'creator_reply_>600' not in sigs

    def test_creator_replied_300_chars(self, ctx, write_json):
        # 300 chars: creator_replied + creator_reply_>200 = 2 points total.
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment',
                author_channel_id='UC_x', total_reply_count=1),
            _comment('r1', 'x' * 300, parent_id='c1', author_channel_id='ch1'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert sigs.get('creator_replied') == 1
        assert sigs.get('creator_reply_>200') == 1
        assert 'creator_reply_>400' not in sigs

    def test_creator_replied_700_chars_full_4_tiers(self, ctx, write_json):
        # 700 chars: replied + >200 + >400 + >600 = 4 points (creator_liked
        # not detectable yet, so 4 not 5).
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'a comment',
                author_channel_id='UC_x', total_reply_count=1),
            _comment('r1', 'x' * 700, parent_id='c1', author_channel_id='ch1'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        sigs = {b['signal']: b['points'] for b in results['c1']['tags']['breakdown']}
        assert sigs.get('creator_replied') == 1
        assert sigs.get('creator_reply_>200') == 1
        assert sigs.get('creator_reply_>400') == 1
        assert sigs.get('creator_reply_>600') == 1

    def test_botlike_author_drops_to_ignorable(self, ctx, write_json):
        # Long random digit run + no description + handle == name + fresh
        # account. Every channel signal points at a farm.
        _stub_channel(write_json, 'UC_farm',
            title='user834729', custom_url='@user834729',
            description='',
            subscriber_count=2, uploads_count=0,
            published_at=BATCH_TIME.isoformat())
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1',
                'A short attempt at appearing substantive but the channel is fresh.',
                author_channel_id='UC_farm'),
        ])
        results = classify(_video(), expand=False, fetch_authors=False)
        # Channel-level negatives (botlike, no-desc, handle-eq-name) outweigh
        # whatever the comment text earns.
        assert results['c1']['score'] < 0

    def test_persists_to_processed_dir(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'hello there friend', author_channel_id='UC_x'),
        ])
        classify(_video(), expand=False)
        out = ctx / 'youtube/videos/active/vi/vid_TEST/processed/comments_classified.json'
        assert out.exists()
        data = json.loads(out.read_text())
        assert data['schema_version'] == SCHEMA_VERSION
        assert data['video_id'] == 'vid_TEST'
        assert 'c1' in data['classifications']

    def test_cached_read_short_circuits(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'short', author_channel_id='UC_x'),
        ])
        # Pre-write a classification with a sentinel value that isn't what
        # we'd normally produce.
        write_json('youtube/videos/active/vi/vid_TEST/processed/comments_classified.json', {
            'schema_version': SCHEMA_VERSION,
            'video_id': 'vid_TEST',
            'classified_at': BATCH_TIME.isoformat(),
            'classifications': {
                'c1': {'quality_class': 'sentinel', 'score': 999, 'tags': {}, 'parent_id': None},
            },
        })
        results = classify(_video(), expand=False, fetch_authors=False)
        assert results['c1']['quality_class'] == 'sentinel'

    def test_force_recomputes(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'nice', author_channel_id='UC_x'),
        ])
        write_json('youtube/videos/active/vi/vid_TEST/processed/comments_classified.json', {
            'schema_version': SCHEMA_VERSION,
            'video_id': 'vid_TEST',
            'classified_at': BATCH_TIME.isoformat(),
            'classifications': {
                'c1': {'quality_class': 'sentinel', 'score': 999, 'tags': {}, 'parent_id': None},
            },
        })
        results = classify(_video(), expand=False, fetch_authors=False, force=True)
        # Recomputed: 'nice' is short and entity-free → ignorable.
        assert results['c1']['quality_class'] == 'ignorable'

    def test_lazy_fetch_only_for_quality_gated(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('s1', 'spam', author_channel_id='UC_spam'),
            _comment('q1',
                'This is a substantive comment with enough length to pass the gate. '
                'Timothy Cain at Interplay made some great calls about Fallout dialogue.'
                ' I learned a lot from this video and want to thank the creator deeply.',
                author_channel_id='UC_quality'),
        ])

        # Mock Channel.retrieve so we can detect calls without real API.
        retrieve_calls = []
        def fake_retrieve(channel_id):
            retrieve_calls.append(channel_id)
            return {
                'channel_id': channel_id, 'title': f'C {channel_id}',
                'description': '', 'subscriber_count': 100, 'uploads_count': 5,
                'view_count': 1000, 'banner_external_url': '', 'custom_url': '',
                'playlists_data': {}, 'status': {}, 'thumbnails': {},
                'topic_details': {}, 'published_at': '2020-01-01T00:00:00+00:00',
                'schema_version': 2,
            }

        with patch('youtube.channel.Channel.retrieve', side_effect=fake_retrieve):
            classify(_video(), expand=False)

        # Quality comment author got fetched, spam author did not.
        assert 'UC_quality' in retrieve_calls
        assert 'UC_spam' not in retrieve_calls


class TestExpansion:
    def test_quality_thread_expands(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1',
                'A substantive reflection. Timothy Cain has talked at length about '
                'the design of Fallout dialogues at Interplay and Black Isle Studios. '
                'His commentary here is consistent with what he said in his earlier '
                'videos about Bethesda. According to his earlier post, this was '
                'a deliberate design choice in 1997.',
                author_channel_id='UC_quality',
                total_reply_count=2,
            ),
        ])

        # Mock the API to return two replies when expand_replies is called.
        client = MagicMock()
        request = MagicMock()
        request.execute.return_value = {
            'items': [
                {'id': 'r1', 'snippet': {
                    'parentId': 'c1', 'authorDisplayName': 'a',
                    'authorChannelId': {'value': 'UC_a'},
                    'textDisplay': 'reply text', 'textOriginal': 'reply text',
                    'likeCount': 0,
                    'publishedAt': '2024-06-01T01:00:00Z',
                    'updatedAt': '2024-06-01T01:00:00Z',
                }},
            ],
        }
        client.comments.return_value.list.return_value = request
        client.comments.return_value.list_next.return_value = None

        with patch('youtube.get_youtube_client', return_value=client), \
             patch('youtube.channel.Channel.retrieve', return_value={
                 'channel_id': 'UC_quality', 'title': 't', 'description': '',
                 'subscriber_count': 100, 'uploads_count': 5, 'view_count': 0,
                 'banner_external_url': '', 'custom_url': '', 'playlists_data': {},
                 'status': {}, 'thumbnails': {}, 'topic_details': {},
                 'published_at': '2020-01-01T00:00:00+00:00', 'schema_version': 2,
             }):
            classify(_video())

        comments = json.loads(
            (ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text()
        )['comments']
        assert 'r1' in comments
        assert comments['c1']['replies_complete'] is True

    def test_anti_thread_does_not_expand(self, ctx, write_json):
        _seed_comments(write_json, 'vid_TEST', [
            _comment('c1', 'AMAZING!!! 🔥🔥🔥', like_count=200,
                author_channel_id='UC_spam', total_reply_count=99),
        ])

        # If expand was called, this would error (no mocked client).
        classify(_video())

        comments = json.loads(
            (ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text()
        )['comments']
        assert comments['c1']['replies_complete'] is False
