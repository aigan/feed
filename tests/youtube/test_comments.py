import json
from unittest.mock import MagicMock, patch

import pytest
from conftest import BATCH_TIME

from youtube.comment import Comment, CommentsDisabledError
from youtube.video import Video


def _thread(comment_id, text='hello', author='alice', author_channel_id='UC_a',
            published_at='2024-06-01T00:00:00Z', updated_at='2024-06-01T00:00:00Z',
            like_count=0, total_reply_count=0, replies=None):
    item = {
        'id': comment_id,
        'snippet': {
            'videoId': 'vid_TEST',
            'totalReplyCount': total_reply_count,
            'topLevelComment': {
                'id': comment_id,
                'snippet': {
                    'authorDisplayName': author,
                    'authorChannelId': {'value': author_channel_id},
                    'textDisplay': text,
                    'textOriginal': text,
                    'likeCount': like_count,
                    'publishedAt': published_at,
                    'updatedAt': updated_at,
                },
            },
        },
    }
    if replies:
        item['replies'] = {'comments': replies}
    return item


def _reply(reply_id, parent_id, text='reply', author='bob', like_count=0,
           published_at='2024-06-01T01:00:00Z', updated_at='2024-06-01T01:00:00Z'):
    return {
        'id': reply_id,
        'snippet': {
            'parentId': parent_id,
            'authorDisplayName': author,
            'authorChannelId': {'value': 'UC_b'},
            'textDisplay': text,
            'textOriginal': text,
            'likeCount': like_count,
            'publishedAt': published_at,
            'updatedAt': updated_at,
        },
    }


def _video():
    return Video(
        video_id='vid_TEST', title='T', channel_id='ch1',
        published_at=BATCH_TIME, first_seen=BATCH_TIME, last_updated=BATCH_TIME,
        description='', thumbnails_data={}, tags=[], category_id=1,
        live_status='none', duration_data='PT1M', spatial_dimension_type='2d',
        resolution_tier='hd', captioned=True, licensed_content=False,
        content_rating_data={}, viewing_projection='rectangular',
        privacy_status='public', license='youtube', embeddable=True,
        public_stats_viewable=True, made_for_kids=False, view_count=0,
        like_count=0, comment_count=0, topic_details={},
        has_paid_product_placement=False,
    )


def _mock_pages(*pages):
    """pages = list of (items, next_page_token). list_next returns None when token is None."""
    mock_client = MagicMock()
    requests = [MagicMock() for _ in pages]
    responses = [{'items': items, **({'nextPageToken': tok} if tok else {})}
                 for items, tok in pages]
    for req, resp in zip(requests, responses):
        req.execute.return_value = resp
    mock_client.commentThreads.return_value.list.return_value = requests[0]

    next_calls = list(zip(requests, responses))

    def list_next(req, resp):
        for idx, (r, rs) in enumerate(next_calls):
            if r is req and rs is resp:
                if resp.get('nextPageToken') and idx + 1 < len(next_calls):
                    return next_calls[idx + 1][0]
                return None
        return None

    mock_client.commentThreads.return_value.list_next.side_effect = list_next
    return mock_client


def _patch_client(mock_client):
    return patch('youtube.get_youtube_client', return_value=mock_client)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

class TestCommentsPaths:
    def test_active_comments_file(self, ctx):
        assert Video.get_active_comments_file('abc123') == \
            ctx / 'youtube/videos/active/ab/abc123/comments.json'

    def test_archive_comments_file(self, ctx):
        assert Video.get_archive_comments_file('abc123', 2) == \
            ctx / 'youtube/videos/archive/ab/abc123/comments-v2.json'

    def test_latest_comments_version_empty(self, ctx):
        assert Video.latest_comments_version('abc123') == 0

    def test_latest_comments_version_with_files(self, ctx, write_json):
        write_json('youtube/videos/archive/vi/vid_TEST/comments-v1.json', {})
        write_json('youtube/videos/archive/vi/vid_TEST/comments-v3.json', {})
        assert Video.latest_comments_version('vid_TEST') == 3


# ---------------------------------------------------------------------------
# Fresh mirror
# ---------------------------------------------------------------------------

class TestMirrorFresh:
    def test_creates_files(self, ctx):
        thread = _thread('c1', text='hi', total_reply_count=1,
            replies=[_reply('r1', 'c1', text='back')])
        client = _mock_pages(([thread], None))

        with _patch_client(client):
            _video().mirror_comments()

        path = ctx / 'youtube/videos/active/vi/vid_TEST/comments.json'
        data = json.loads(path.read_text())
        assert data['comments_disabled'] is False
        assert data['fetch_complete'] is True
        assert data['next_page_token'] is None
        assert data['pages_fetched'] == 1
        assert set(data['comments']) == {'c1', 'r1'}
        assert data['comments']['c1']['parent_id'] is None
        assert data['comments']['r1']['parent_id'] == 'c1'
        assert data['comments']['c1']['first_seen'] == BATCH_TIME.isoformat()
        assert data['comments']['c1']['last_seen'] == BATCH_TIME.isoformat()

        txt = (ctx / 'youtube/videos/active/vi/vid_TEST/comments.txt').read_text()
        assert '[c1]' in txt
        assert '[r1]' in txt
        assert 'hi' in txt
        assert 'back' in txt

    def test_no_archive_on_fresh(self, ctx):
        client = _mock_pages(([_thread('c1')], None))
        with _patch_client(client):
            _video().mirror_comments()
        archive_dir = ctx / 'youtube/videos/archive/vi/vid_TEST'
        assert not list(archive_dir.glob('comments-v*.json')) if archive_dir.exists() else True


# ---------------------------------------------------------------------------
# Comments disabled
# ---------------------------------------------------------------------------

class TestCommentsDisabled:
    def _disabled_error(self):
        from googleapiclient.errors import HttpError
        resp = MagicMock()
        resp.status = 403
        e = HttpError(resp=resp, content=b'{"error":{"errors":[{"reason":"commentsDisabled"}]}}')
        e.error_details = [{'reason': 'commentsDisabled'}]
        return e

    def test_disabled_marks_flag(self, ctx):
        client = MagicMock()
        request = MagicMock()
        request.execute.side_effect = self._disabled_error()
        client.commentThreads.return_value.list.return_value = request

        with _patch_client(client):
            _video().mirror_comments()

        path = ctx / 'youtube/videos/active/vi/vid_TEST/comments.json'
        data = json.loads(path.read_text())
        assert data['comments_disabled'] is True
        assert data['fetch_complete'] is True
        assert data['comments'] == {}

    def test_disabled_preserves_existing_comments(self, ctx, write_json):
        write_json('youtube/videos/active/vi/vid_TEST/comments.json', {
            'comments_disabled': False,
            'fetched_at': '2024-01-01T00:00:00+00:00',
            'fetch_complete': True,
            'next_page_token': None,
            'pages_fetched': 1,
            'comments': {
                'old1': {'comment_id': 'old1', 'video_id': 'vid_TEST',
                    'parent_id': None, 'author_display_name': 'x',
                    'author_channel_id': None, 'text_display': 'kept',
                    'text_original': 'kept', 'like_count': 0,
                    'published_at': '2024-01-01T00:00:00Z',
                    'updated_at': '2024-01-01T00:00:00Z',
                    'total_reply_count': 0,
                    'first_seen': '2024-01-01T00:00:00+00:00',
                    'last_seen': '2024-01-01T00:00:00+00:00'},
            },
        })
        client = MagicMock()
        request = MagicMock()
        request.execute.side_effect = self._disabled_error()
        client.commentThreads.return_value.list.return_value = request

        with _patch_client(client):
            _video().mirror_comments(force=True)

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert data['comments_disabled'] is True
        assert 'old1' in data['comments']


# ---------------------------------------------------------------------------
# Re-fetch behavior
# ---------------------------------------------------------------------------

class TestRefetchBehavior:
    def test_no_changes_no_archive(self, ctx, write_json):
        thread = _thread('c1', text='hi')
        # First mirror
        with _patch_client(_mock_pages(([thread], None))):
            _video().mirror_comments()
        # Second mirror — same content; force re-fetch since cache is complete
        with _patch_client(_mock_pages(([thread], None))):
            _video().mirror_comments(force=True)
        archive_dir = ctx / 'youtube/videos/archive/vi/vid_TEST'
        assert not (archive_dir.exists() and list(archive_dir.glob('comments-v*.json')))

    def test_edit_triggers_archive(self, ctx):
        with _patch_client(_mock_pages(([_thread('c1', text='original')], None))):
            _video().mirror_comments()
        with _patch_client(_mock_pages(([_thread('c1', text='edited')], None))):
            _video().mirror_comments(force=True)

        archive_path = ctx / 'youtube/videos/archive/vi/vid_TEST/comments-v1.json'
        assert archive_path.exists()
        archived = json.loads(archive_path.read_text())
        assert archived['comments']['c1']['text_display'] == 'original'

        active = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert active['comments']['c1']['text_display'] == 'edited'

    def test_like_count_change_no_archive(self, ctx):
        with _patch_client(_mock_pages(([_thread('c1', like_count=1)], None))):
            _video().mirror_comments()
        with _patch_client(_mock_pages(([_thread('c1', like_count=99)], None))):
            _video().mirror_comments(force=True)
        archive_dir = ctx / 'youtube/videos/archive/vi/vid_TEST'
        assert not (archive_dir.exists() and list(archive_dir.glob('comments-v*.json')))

    def test_missing_comment_preserved(self, ctx):
        with _patch_client(_mock_pages(([_thread('c1'), _thread('c2')], None))):
            _video().mirror_comments()
        with _patch_client(_mock_pages(([_thread('c1')], None))):
            _video().mirror_comments(force=True)

        active = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert 'c1' in active['comments']
        assert 'c2' in active['comments']
        # c2's last_seen unchanged from first mirror; both first_seen equal BATCH_TIME
        assert active['comments']['c2']['last_seen'] == BATCH_TIME.isoformat()
        archive_dir = ctx / 'youtube/videos/archive/vi/vid_TEST'
        assert not (archive_dir.exists() and list(archive_dir.glob('comments-v*.json')))

    def test_new_comment_appended_no_archive(self, ctx):
        with _patch_client(_mock_pages(([_thread('c1')], None))):
            _video().mirror_comments()
        with _patch_client(_mock_pages(([_thread('c1'), _thread('c2')], None))):
            _video().mirror_comments(force=True)

        active = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert {'c1', 'c2'} <= set(active['comments'])
        archive_dir = ctx / 'youtube/videos/archive/vi/vid_TEST'
        assert not (archive_dir.exists() and list(archive_dir.glob('comments-v*.json')))


# ---------------------------------------------------------------------------
# Partial fetch / auto-resume
# ---------------------------------------------------------------------------

class TestPartialFetch:
    def test_limit_caps(self, ctx):
        client = _mock_pages(
            ([_thread('c1')], 'tok2'),
            ([_thread('c2')], 'tok3'),
            ([_thread('c3')], None),
        )
        with _patch_client(client):
            _video().mirror_comments(comment_limit=1)

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert data['fetch_complete'] is False
        assert data['next_page_token'] == 'tok2'
        assert data['pages_fetched'] == 1
        assert set(data['comments']) == {'c1'}

    def test_auto_resume_when_incomplete(self, ctx):
        client1 = _mock_pages(
            ([_thread('c1')], 'tok2'),
            ([_thread('c2')], None),
        )
        with _patch_client(client1):
            _video().mirror_comments(comment_limit=1)

        client2 = MagicMock()
        req2 = MagicMock()
        req2.execute.return_value = {'items': [_thread('c2')]}
        client2.commentThreads.return_value.list.return_value = req2
        client2.commentThreads.return_value.list_next.return_value = None

        with _patch_client(client2):
            _video().mirror_comments()

        client2.commentThreads.return_value.list.assert_called_with(
            videoId='vid_TEST', part='snippet,replies', maxResults=100,
            textFormat='plainText', pageToken='tok2',
        )

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert data['fetch_complete'] is True
        assert data['next_page_token'] is None
        assert data['pages_fetched'] == 2
        assert set(data['comments']) == {'c1', 'c2'}

    def test_skips_when_complete(self, ctx):
        with _patch_client(_mock_pages(([_thread('c1')], None))):
            _video().mirror_comments()

        client = MagicMock()
        with _patch_client(client):
            _video().mirror_comments()
        client.commentThreads.return_value.list.assert_not_called()

    def test_force_restarts_from_scratch(self, ctx):
        client1 = _mock_pages(
            ([_thread('c1')], 'tok2'),
            ([_thread('c2')], None),
        )
        with _patch_client(client1):
            _video().mirror_comments(comment_limit=1)

        client2 = _mock_pages(([_thread('c1')], None))
        with _patch_client(client2):
            _video().mirror_comments(force=True)

        # No pageToken — fresh start despite the previous incomplete state
        client2.commentThreads.return_value.list.assert_called_with(
            videoId='vid_TEST', part='snippet,replies', maxResults=100,
            textFormat='plainText',
        )

    def test_mid_fetch_exception_persists_partial(self, ctx):
        client = MagicMock()
        req1 = MagicMock()
        req1.execute.return_value = {'items': [_thread('c1')], 'nextPageToken': 'tok2'}
        req2 = MagicMock()
        req2.execute.side_effect = RuntimeError('network blip')
        client.commentThreads.return_value.list.return_value = req1
        client.commentThreads.return_value.list_next.return_value = req2

        with _patch_client(client):
            with pytest.raises(RuntimeError):
                _video().mirror_comments()

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert data['fetch_complete'] is False
        assert data['next_page_token'] == 'tok2'
        assert data['pages_fetched'] == 1
        assert set(data['comments']) == {'c1'}


# ---------------------------------------------------------------------------
# local_comments / Comment.replies
# ---------------------------------------------------------------------------

class TestLocalComments:
    def test_returns_comment_instances(self, ctx):
        thread = _thread('c1', total_reply_count=1, replies=[_reply('r1', 'c1')])
        with _patch_client(_mock_pages(([thread], None))):
            _video().mirror_comments()

        comments = _video().local_comments()
        assert len(comments) == 2
        assert all(isinstance(c, Comment) for c in comments)
        top = next(c for c in comments if c.is_top_level)
        assert top.comment_id == 'c1'
        reply = next(c for c in comments if not c.is_top_level)
        assert reply.parent_id == 'c1'

    def test_replies_filters_to_direct_children(self, ctx):
        thread = _thread('c1', total_reply_count=2,
            replies=[_reply('r1', 'c1', text='one'), _reply('r2', 'c1', text='two')])
        thread2 = _thread('c2', text='other top-level')
        with _patch_client(_mock_pages(([thread, thread2], None))):
            _video().mirror_comments()

        comments = _video().local_comments()
        c1 = next(c for c in comments if c.comment_id == 'c1')
        replies = c1.replies()
        assert {r.comment_id for r in replies} == {'r1', 'r2'}

    def test_empty_when_no_file(self, ctx):
        assert _video().local_comments() == []


# ---------------------------------------------------------------------------
# expand_replies (deep fetch a single thread)
# ---------------------------------------------------------------------------

def _comments_list_pages(*pages):
    """pages = list of (reply_items, next_page_token)."""
    mock_client = MagicMock()
    requests = [MagicMock() for _ in pages]
    responses = [{'items': items, **({'nextPageToken': tok} if tok else {})}
                 for items, tok in pages]
    for req, resp in zip(requests, responses):
        req.execute.return_value = resp
    mock_client.comments.return_value.list.return_value = requests[0]

    next_calls = list(zip(requests, responses))

    def list_next(req, resp):
        for idx, (r, rs) in enumerate(next_calls):
            if r is req and rs is resp:
                if resp.get('nextPageToken') and idx + 1 < len(next_calls):
                    return next_calls[idx + 1][0]
                return None
        return None

    mock_client.comments.return_value.list_next.side_effect = list_next
    return mock_client


def _seed_top_level(ctx, comment_id='c1'):
    with _patch_client(_mock_pages(([_thread(comment_id, total_reply_count=12)], None))):
        _video().mirror_comments()


class TestExpandReplies:
    def test_fetches_all_replies_and_marks_complete(self, ctx):
        _seed_top_level(ctx)
        client = _comments_list_pages(
            ([_reply('r1', 'c1'), _reply('r2', 'c1')], 'tok'),
            ([_reply('r3', 'c1')], None),
        )
        with _patch_client(client):
            _video().expand_replies('c1')

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert {'c1', 'r1', 'r2', 'r3'} <= set(data['comments'])
        assert data['comments']['c1']['replies_complete'] is True
        assert data['comments']['r1']['parent_id'] == 'c1'
        assert data['comments']['r1']['replies_complete'] is False

    def test_idempotent_when_complete(self, ctx):
        _seed_top_level(ctx)
        with _patch_client(_comments_list_pages(([_reply('r1', 'c1')], None))):
            _video().expand_replies('c1')

        client = MagicMock()
        with _patch_client(client):
            _video().expand_replies('c1')
        client.comments.return_value.list.assert_not_called()

    def test_force_refetches(self, ctx):
        _seed_top_level(ctx)
        with _patch_client(_comments_list_pages(([_reply('r1', 'c1')], None))):
            _video().expand_replies('c1')

        client = _comments_list_pages(([_reply('r1', 'c1'), _reply('r2', 'c1')], None))
        with _patch_client(client):
            _video().expand_replies('c1', force=True)

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert {'r1', 'r2'} <= set(data['comments'])

    def test_errors_when_comment_not_in_cache(self, ctx):
        _seed_top_level(ctx, 'c1')
        with pytest.raises(ValueError, match='not in cache'):
            _video().expand_replies('unknown_id')

    def test_errors_when_id_is_a_reply(self, ctx):
        with _patch_client(_mock_pages(([_thread('c1', total_reply_count=1,
                replies=[_reply('r1', 'c1')])], None))):
            _video().mirror_comments()

        with pytest.raises(ValueError, match='reply'):
            _video().expand_replies('r1')

    def test_errors_when_no_cache(self, ctx):
        with pytest.raises(ValueError, match='mirror first'):
            _video().expand_replies('c1')

    def test_replies_complete_does_not_trigger_archive(self, ctx):
        _seed_top_level(ctx)
        with _patch_client(_comments_list_pages(([_reply('r1', 'c1')], None))):
            _video().expand_replies('c1')

        archive_dir = ctx / 'youtube/videos/archive/vi/vid_TEST'
        assert not (archive_dir.exists() and list(archive_dir.glob('comments-v*.json')))

    def test_replies_complete_preserved_across_shallow_refetch(self, ctx):
        _seed_top_level(ctx)
        with _patch_client(_comments_list_pages(([_reply('r1', 'c1')], None))):
            _video().expand_replies('c1')

        with _patch_client(_mock_pages(([_thread('c1', total_reply_count=12)], None))):
            _video().mirror_comments(force=True)

        data = json.loads((ctx / 'youtube/videos/active/vi/vid_TEST/comments.json').read_text())
        assert data['comments']['c1']['replies_complete'] is True
        assert 'r1' in data['comments']
