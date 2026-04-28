import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from conftest import BATCH_TIME

from analysis.ytapi_video_extractor import YTAPIVideoExtractor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANNED_EXTRACT_RESPONSE = """\
=== FORMAT ===
monologue

=== EPISODE ===
none

=== SPEAKERS ===
John Doe | host | tech reviewer

=== ENTITIES ===
John Doe | person |

=== CONCEPTS ===
testing | Software testing methodology

=== RELATIONSHIPS ===
John Doe + testing | Host discusses testing

=== SOURCES ==="""

CANNED_SECTION_RESPONSES = [
    'monologue',
    'none',
    'John Doe | host | tech reviewer',
    'John Doe | person |',
    'testing | Software testing methodology',
    'John Doe + testing | Host discusses testing',
    '',
]

CANNED_EVAL_RESPONSE = """\
COVERAGE: minimal

GAPS:
- Cannot determine production quality from metadata

SUPPORTED:
- Speaker identified from title

VALUE: insufficient metadata

VERDICT: need_transcript"""


def _mock_conversation(section_responses):
    conv = MagicMock()
    conv.ask = MagicMock(side_effect=list(section_responses))
    return conv


def _make_video_mock(**overrides):
    """Create a mock video object for testing."""
    video = MagicMock()
    video.video_id = overrides.get("video_id", "vid_ext_test")
    video.title = overrides.get("title", "Test Video")
    video.description = overrides.get("description", "0:00 Intro\n2:00 Main topic")
    video.published_at = overrides.get("published_at", datetime(2024, 6, 1))
    video.duration_formatted = overrides.get("duration_formatted", "10:00")
    video.tags = overrides.get("tags", ["tag1", "tag2"])
    video.last_updated = overrides.get("last_updated", BATCH_TIME)
    video.channel.title = overrides.get("channel_title", "Test Channel")
    video.duration_seconds = overrides.get("duration_seconds", 600)
    return video


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.run
# ---------------------------------------------------------------------------

class TestYTAPIVideoExtractorRun:
    def test_run_stores_result_and_returns_dict(self, ctx):
        video = _make_video_mock()
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv), \
             patch.object(YTAPIVideoExtractor, 'ask_llm', return_value=CANNED_EVAL_RESPONSE):
            result = YTAPIVideoExtractor.run(video)

        assert result['video_id'] == 'vid_ext_test'
        assert result['prompt_version'] == YTAPIVideoExtractor.PROMPT_VERSION
        assert 'FORMAT:' in result['text']
        assert result['extracted_at'] == BATCH_TIME.isoformat()

        result_file = ctx / 'youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json'
        assert result_file.exists()

    def test_run_passes_video_metadata_to_conversation(self, ctx):
        video = _make_video_mock(title='Special Title', tags=['python', 'review'])
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv), \
             patch.object(YTAPIVideoExtractor, 'ask_llm', return_value=CANNED_EVAL_RESPONSE):
            YTAPIVideoExtractor.run(video)

        conv.system.assert_called_once()
        system_text = conv.system.call_args[0][0]
        assert 'Special Title' in system_text
        assert 'python, review' in system_text
        assert '10:00' in system_text


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.get
# ---------------------------------------------------------------------------

class TestYTAPIVideoExtractorGet:
    def test_get_returns_cached_when_fresh(self, ctx, write_json):
        video = _make_video_mock()
        cached = {
            "video_id": "vid_ext_test",
            "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": "cached result",
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        result = YTAPIVideoExtractor.get(video)
        assert result["text"] == "cached result"

    def test_get_reruns_when_prompt_version_differs(self, ctx, write_json):
        video = _make_video_mock()
        cached = {
            'video_id': 'vid_ext_test',
            'prompt_version': 0,
            'video_last_updated': BATCH_TIME.isoformat(),
            'text': 'stale result',
            'extracted_at': BATCH_TIME.isoformat(),
        }
        write_json('youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json', cached)

        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv), \
             patch.object(YTAPIVideoExtractor, 'ask_llm', return_value=CANNED_EVAL_RESPONSE):
            result = YTAPIVideoExtractor.get(video)

        assert 'FORMAT:' in result['text']
        assert result['prompt_version'] == YTAPIVideoExtractor.PROMPT_VERSION


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.get_description_timestamps
# ---------------------------------------------------------------------------

class TestGetDescriptionTimestamps:
    def test_plain_mm_ss_format(self):
        video = _make_video_mock(
            description="0:00 Intro\n2:00 Main topic\n10:00 Outro"
        )
        chapters = YTAPIVideoExtractor.get_description_timestamps(video)
        assert chapters == [
            [0, "Intro"],
            [120, "Main topic"],
            [600, "Outro"],
        ]

    def test_bracketed_chapters_survive(self):
        # Real-world case: `[00:00] Introduction` — the filter strips this
        # block in some channels, so get_description_timestamps must read
        # video.description directly rather than relying on the stripped
        # context or a cached JSON.
        description = (
            "Some intro prose.\n\n"
            "Chapters:\n"
            "[00:00] Introduction\n"
            "[01:28] About Facade\n"
            "[08:36] The Design\n"
            "[25:49] Closing\n"
        )
        video = _make_video_mock(description=description)
        chapters = YTAPIVideoExtractor.get_description_timestamps(video)
        assert chapters == [
            [0, "Introduction"],
            [88, "About Facade"],
            [516, "The Design"],
            [1549, "Closing"],
        ]

    def test_hhmmss_format(self):
        video = _make_video_mock(description="0:00 Start\n1:02:30 Long section")
        chapters = YTAPIVideoExtractor.get_description_timestamps(video)
        assert chapters == [
            [0, "Start"],
            [3750, "Long section"],
        ]

    def test_ignores_cached_ytapi_extracted_json(self, ctx, write_json):
        # Even if a stale cached JSON exists with different timestamps, the
        # new contract reads straight from video.description.
        video = _make_video_mock(description="0:00 Fresh intro\n5:00 Fresh middle")
        write_json(
            "youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json",
            {
                "video_id": "vid_ext_test",
                "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
                "video_last_updated": BATCH_TIME.isoformat(),
                "text": "IGNORED",
                "extracted_at": BATCH_TIME.isoformat(),
            },
        )
        chapters = YTAPIVideoExtractor.get_description_timestamps(video)
        assert chapters == [[0, "Fresh intro"], [300, "Fresh middle"]]


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.get  — edge cases
# ---------------------------------------------------------------------------

class TestExtractorGetEdgeCases:
    def test_get_cached_missing_prompt_version_raises(self, ctx, write_json):
        video = _make_video_mock()
        cached = {
            "video_id": "vid_ext_test",
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": "some result",
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        with pytest.raises(KeyError):
            YTAPIVideoExtractor.get(video)

    def test_get_cached_corrupted_json_raises(self, ctx, write_raw):
        video = _make_video_mock()
        write_raw("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json",
                   "NOT JSON{{{")

        with pytest.raises(json.JSONDecodeError):
            YTAPIVideoExtractor.get(video)

    def test_get_stale_video_updated_reruns(self, ctx, write_json):
        video = _make_video_mock()
        old_time = datetime(2023, 1, 1, tzinfo=timezone.utc)
        cached = {
            'video_id': 'vid_ext_test',
            'prompt_version': YTAPIVideoExtractor.PROMPT_VERSION,
            'video_last_updated': old_time.isoformat(),
            'text': 'stale result',
            'extracted_at': old_time.isoformat(),
        }
        write_json('youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json', cached)

        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv), \
             patch.object(YTAPIVideoExtractor, 'ask_llm', return_value=CANNED_EVAL_RESPONSE):
            result = YTAPIVideoExtractor.get(video)

        assert 'FORMAT:' in result['text']


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.get_description_timestamps  — edge cases
# ---------------------------------------------------------------------------

class TestGetDescriptionTimestampsEdgeCases:
    def test_description_with_no_timestamps_returns_empty(self):
        video = _make_video_mock(description="Just some text, no chapters at all.")
        assert YTAPIVideoExtractor.get_description_timestamps(video) == []

    def test_empty_description_returns_empty(self):
        video = _make_video_mock(description="")
        assert YTAPIVideoExtractor.get_description_timestamps(video) == []

    def test_solo_timestamp_without_title_returns_empty(self):
        # A bare `0:00` with nothing else on the line is not a useful
        # chapter marker; the helper should ignore it.
        video = _make_video_mock(description="0:00")
        assert YTAPIVideoExtractor.get_description_timestamps(video) == []


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor._parse_sections
# ---------------------------------------------------------------------------


EXPECTED_STRICT_SECTIONS = {
    'FORMAT': 'monologue',
    'EPISODE': 'none',
    'SPEAKERS': 'John Doe | host | tech reviewer',
    'ENTITIES': 'John Doe | person |',
    'CONCEPTS': 'testing | Software testing methodology',
    'RELATIONSHIPS': 'John Doe + testing | Host discusses testing',
    'SOURCES': '',
}


class TestParseSections:
    def test_strict_form_round_trips(self):
        sections = YTAPIVideoExtractor._parse_sections(CANNED_EXTRACT_RESPONSE)
        assert sections == EXPECTED_STRICT_SECTIONS

    def test_markdown_fence_wrapper_plain(self):
        wrapped = f"```\n{CANNED_EXTRACT_RESPONSE}\n```"
        sections = YTAPIVideoExtractor._parse_sections(wrapped)
        assert sections == EXPECTED_STRICT_SECTIONS

    def test_markdown_fence_wrapper_with_language(self):
        wrapped = f"```text\n{CANNED_EXTRACT_RESPONSE}\n```"
        sections = YTAPIVideoExtractor._parse_sections(wrapped)
        assert sections == EXPECTED_STRICT_SECTIONS

    def test_colon_form_delimiters(self):
        text = (
            "FORMAT:\nmonologue\n\n"
            "EPISODE:\nnone\n\n"
            "SPEAKERS:\nJohn Doe | host | tech reviewer\n\n"
            "ENTITIES:\nJohn Doe | person |\n\n"
            "CONCEPTS:\ntesting | Software testing methodology\n\n"
            "RELATIONSHIPS:\nJohn Doe + testing | Host discusses testing\n\n"
            "SOURCES:"
        )
        sections = YTAPIVideoExtractor._parse_sections(text)
        assert sections == EXPECTED_STRICT_SECTIONS

    def test_markdown_heading_delimiters(self):
        text = (
            "## FORMAT\nmonologue\n\n"
            "## EPISODE\nnone\n\n"
            "## SPEAKERS\nJohn Doe | host | tech reviewer\n\n"
            "## ENTITIES\nJohn Doe | person |\n\n"
            "## CONCEPTS\ntesting | Software testing methodology\n\n"
            "## RELATIONSHIPS\nJohn Doe + testing | Host discusses testing\n\n"
            "## SOURCES"
        )
        sections = YTAPIVideoExtractor._parse_sections(text)
        assert sections == EXPECTED_STRICT_SECTIONS

    def test_unknown_colon_token_not_matched(self):
        # A pipe-delimited line with an unknown colon-prefixed token must
        # stay inside its section instead of being treated as a delimiter.
        text = (
            "=== ENTITIES ===\n"
            "SOMETHING: | person | unrelated\n"
            "Other Person | person |"
        )
        sections = YTAPIVideoExtractor._parse_sections(text)
        assert 'ENTITIES' in sections
        assert 'SOMETHING' not in sections
        assert 'SOMETHING: | person | unrelated' in sections['ENTITIES']

    def test_empty_parse_emits_warning(self, ctx, capsys):
        gibberish = 'the model rambled without any structured output at all'
        YTAPIVideoExtractor._parse_extraction(gibberish)
        captured = capsys.readouterr()
        assert 'no recognizable sections' in captured.out
        assert 'rambled' in captured.out


# ---------------------------------------------------------------------------
# Conversation
# ---------------------------------------------------------------------------

class TestConversation:
    def test_accumulates_messages(self):
        from analysis.processor import Conversation
        with patch('langchain_openai.ChatOpenAI') as MockLLM:
            mock_response = MagicMock()
            mock_response.content = 'answer1'
            MockLLM.return_value.invoke.return_value = mock_response

            conv = Conversation(profile='extract')
            result = conv.ask('question1')

        assert result == 'answer1'
        assert len(conv.messages) == 2  # human + ai

    def test_system_message_prepended(self):
        from analysis.processor import Conversation
        with patch('langchain_openai.ChatOpenAI') as MockLLM:
            mock_response = MagicMock()
            mock_response.content = 'answer'
            MockLLM.return_value.invoke.return_value = mock_response

            conv = Conversation(profile='extract')
            conv.system('you are a helper')
            conv.ask('question')

        assert len(conv.messages) == 3  # system + human + ai
        assert conv.messages[0].content == 'you are a helper'


# ---------------------------------------------------------------------------
# Multi-turn _step_extract
# ---------------------------------------------------------------------------

class TestStepExtractMultiTurn:
    def test_calls_conversation_per_section(self, ctx):
        video = _make_video_mock()
        context = YTAPIVideoExtractor._build_context(video)
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv):
            YTAPIVideoExtractor._step_extract(context)

        assert conv.system.call_count == 1
        assert conv.ask.call_count == 7

    def test_parses_all_sections(self, ctx):
        video = _make_video_mock()
        context = YTAPIVideoExtractor._build_context(video)
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv):
            result = YTAPIVideoExtractor._step_extract(context)

        assert result['formats'] == ['monologue']
        assert result['episode'] is None
        assert result['speakers'] == [{'name': 'John Doe', 'role': 'host', 'description': 'tech reviewer'}]
        assert result['entities'] == [{'name': 'John Doe', 'category': 'person', 'aliases': ''}]
        assert result['concepts'] == [{'keyword': 'testing', 'description': 'Software testing methodology'}]
        assert result['relationships'] == [{'entities': 'John Doe + testing', 'description': 'Host discusses testing'}]
        assert result['sources'] == []

    def test_raw_text_has_section_headers(self, ctx):
        video = _make_video_mock()
        context = YTAPIVideoExtractor._build_context(video)
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv):
            result = YTAPIVideoExtractor._step_extract(context)

        assert '=== FORMAT ===' in result['_raw']
        assert '=== ENTITIES ===' in result['_raw']
        assert '=== SOURCES ===' in result['_raw']

    def test_category_trailing_pipe_stripped(self, ctx):
        responses = list(CANNED_SECTION_RESPONSES)
        responses[3] = 'Wayward Radio | workseries | | \nTed | person | |'
        video = _make_video_mock()
        context = YTAPIVideoExtractor._build_context(video)
        conv = _mock_conversation(responses)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv):
            result = YTAPIVideoExtractor._step_extract(context)

        for entity in result['entities']:
            assert not entity['category'].endswith('|')

    def test_system_message_contains_metadata(self, ctx):
        video = _make_video_mock(title='Special Title', tags=['python'])
        context = YTAPIVideoExtractor._build_context(video)
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv):
            YTAPIVideoExtractor._step_extract(context)

        system_text = conv.system.call_args[0][0]
        assert 'Special Title' in system_text
        assert 'python' in system_text


# ---------------------------------------------------------------------------
# _should_trace
# ---------------------------------------------------------------------------

class TestShouldTrace:
    def test_returns_false_when_no_sources(self):
        extracted = {'formats': ['discussion'], 'sources': []}
        assert YTAPIVideoExtractor._should_trace(extracted) is False

    def test_returns_true_for_trace_format(self):
        extracted = {'formats': ['news'], 'sources': []}
        assert YTAPIVideoExtractor._should_trace(extracted) is True

    def test_returns_true_for_sources_without_urls(self):
        extracted = {
            'formats': ['discussion'],
            'sources': [{'description': 'Some article', 'clues': 'mentioned', 'url': None}],
        }
        assert YTAPIVideoExtractor._should_trace(extracted) is True

    def test_returns_false_for_phantom_none_sources_after_parsing(self):
        responses = {
            'FORMAT': 'discussion',
            'EPISODE': 'none',
            'SPEAKERS': '',
            'ENTITIES': '',
            'CONCEPTS': '',
            'RELATIONSHIPS': '',
            'SOURCES': 'none | no external sources cited | none',
        }
        extracted = YTAPIVideoExtractor._parse_section_responses(responses)
        assert YTAPIVideoExtractor._should_trace(extracted) is False


# ---------------------------------------------------------------------------
# Source filtering in _parse_section_responses
# ---------------------------------------------------------------------------

class TestSourceFiltering:
    def test_filters_none_description_sources(self):
        responses = {
            'FORMAT': 'discussion',
            'EPISODE': 'none',
            'SPEAKERS': '',
            'ENTITIES': '',
            'CONCEPTS': '',
            'RELATIONSHIPS': '',
            'SOURCES': 'none | no external sources cited | none',
        }
        result = YTAPIVideoExtractor._parse_section_responses(responses)
        assert result['sources'] == []

    def test_keeps_real_sources(self):
        responses = {
            'FORMAT': 'news',
            'EPISODE': 'none',
            'SPEAKERS': '',
            'ENTITIES': '',
            'CONCEPTS': '',
            'RELATIONSHIPS': '',
            'SOURCES': 'Nature paper | Smith 2024 | https://doi.org/example',
        }
        result = YTAPIVideoExtractor._parse_section_responses(responses)
        assert len(result['sources']) == 1
        assert result['sources'][0]['description'] == 'Nature paper'


# ---------------------------------------------------------------------------
# run() integration: phantom sources + evaluation raw file
# ---------------------------------------------------------------------------

class TestRunSourceTraceAndEvalFile:
    def test_run_skips_trace_for_phantom_sources(self, ctx):
        responses = list(CANNED_SECTION_RESPONSES)
        responses[6] = 'none | no external sources cited | none'
        video = _make_video_mock()
        conv = _mock_conversation(responses)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv), \
             patch.object(YTAPIVideoExtractor, 'ask_llm', return_value=CANNED_EVAL_RESPONSE) as mock_eval:
            result = YTAPIVideoExtractor.run(video)

        assert result['source_trace'] is None
        mock_eval.assert_called_once()

    def test_run_writes_evaluation_raw_file(self, ctx):
        video = _make_video_mock()
        conv = _mock_conversation(CANNED_SECTION_RESPONSES)
        with patch.object(YTAPIVideoExtractor, 'conversation', return_value=conv), \
             patch.object(YTAPIVideoExtractor, 'ask_llm', return_value=CANNED_EVAL_RESPONSE):
            YTAPIVideoExtractor.run(video)

        eval_file = ctx / 'youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted_evaluation.txt'
        assert eval_file.exists()
        assert eval_file.read_text() == CANNED_EVAL_RESPONSE
