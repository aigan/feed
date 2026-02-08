import json
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from analysis.ytapi_video_extractor import YTAPIVideoExtractor
from conftest import BATCH_TIME


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CANNED_LLM_RESPONSE = """\
FORMAT:
monologue [!]

EPISODE:
none [???]

SPEAKERS:
John Doe: host, tech reviewer [!]

TIMESTAMPS:
0: Introduction [!]
120: Main topic [!]
600: Conclusion [!]

ENTITIES:
John Doe (person) [!]

CONCEPTS:
testing: Software testing methodology [!]

RELATIONSHIPS:
John Doe + testing: Host discusses testing [!]

SOURCES:
none [???]

VALUE:
insight 3 [??]
novelty 3 [??]
quality 3 [??]
delivery 3 [??]
"""


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
    return video


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.run
# ---------------------------------------------------------------------------

class TestYTAPIVideoExtractorRun:
    def test_run_stores_result_and_returns_dict(self, ctx):
        video = _make_video_mock()
        with patch.object(YTAPIVideoExtractor, "ask_llm", return_value=CANNED_LLM_RESPONSE):
            result = YTAPIVideoExtractor.run(video)

        assert result["video_id"] == "vid_ext_test"
        assert result["prompt_version"] == YTAPIVideoExtractor.PROMPT_VERSION
        assert result["text"] == CANNED_LLM_RESPONSE
        assert result["extracted_at"] == BATCH_TIME.isoformat()

        # File should be written
        result_file = ctx / "youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json"
        assert result_file.exists()

    def test_run_passes_video_metadata_to_llm(self, ctx):
        video = _make_video_mock(title="Special Title", tags=["a", "b"])
        call_args = {}

        def capture_llm(prompt, params, **kwargs):
            call_args.update(params)
            return CANNED_LLM_RESPONSE

        with patch.object(YTAPIVideoExtractor, "ask_llm", side_effect=capture_llm):
            YTAPIVideoExtractor.run(video)

        assert call_args["title"] == "Special Title"
        assert call_args["tags"] == "a, b"
        assert call_args["length"] == "10:00"


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
            "video_id": "vid_ext_test",
            "prompt_version": 0,  # old version
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": "stale result",
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        with patch.object(YTAPIVideoExtractor, "ask_llm", return_value=CANNED_LLM_RESPONSE):
            result = YTAPIVideoExtractor.get(video)

        assert result["text"] == CANNED_LLM_RESPONSE
        assert result["prompt_version"] == YTAPIVideoExtractor.PROMPT_VERSION


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.get_chapters
# ---------------------------------------------------------------------------

class TestGetChapters:
    def test_parses_timestamps_from_llm_output(self, ctx, write_json):
        video = _make_video_mock()
        cached = {
            "video_id": "vid_ext_test",
            "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": CANNED_LLM_RESPONSE,
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        chapters = YTAPIVideoExtractor.get_chapters(video)
        assert len(chapters) == 3
        assert chapters[0] == [0, "Introduction [!]"]
        assert chapters[1] == [120, "Main topic [!]"]
        assert chapters[2] == [600, "Conclusion [!]"]


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
            "video_id": "vid_ext_test",
            "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
            "video_last_updated": old_time.isoformat(),
            "text": "stale result",
            "extracted_at": old_time.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        with patch.object(YTAPIVideoExtractor, "ask_llm", return_value=CANNED_LLM_RESPONSE):
            result = YTAPIVideoExtractor.get(video)

        assert result["text"] == CANNED_LLM_RESPONSE


# ---------------------------------------------------------------------------
# YTAPIVideoExtractor.get_chapters  — edge cases
# ---------------------------------------------------------------------------

class TestGetChaptersEdgeCases:
    def test_no_timestamps_section_returns_empty(self, ctx, write_json):
        video = _make_video_mock()
        cached = {
            "video_id": "vid_ext_test",
            "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": "FORMAT:\nmonologue [!]\n\nSPEAKERS:\nnone",
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        assert YTAPIVideoExtractor.get_chapters(video) == []

    def test_empty_timestamps_section_returns_empty(self, ctx, write_json):
        video = _make_video_mock()
        cached = {
            "video_id": "vid_ext_test",
            "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": "TIMESTAMPS:\n\nSPEAKERS:\nnone",
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        assert YTAPIVideoExtractor.get_chapters(video) == []

    def test_malformed_timestamps_absorbed_into_previous(self, ctx, write_json):
        # Non-numeric lines between timestamps get absorbed into the previous chapter's description
        video = _make_video_mock()
        text = "TIMESTAMPS:\n0: Valid chapter [!]\nabc: Invalid [!]\n120: Also valid [!]\n\nSPEAKERS:"
        cached = {
            "video_id": "vid_ext_test",
            "prompt_version": YTAPIVideoExtractor.PROMPT_VERSION,
            "video_last_updated": BATCH_TIME.isoformat(),
            "text": text,
            "extracted_at": BATCH_TIME.isoformat(),
        }
        write_json("youtube/videos/active/vi/vid_ext_test/processed/ytapi_extracted.json", cached)

        chapters = YTAPIVideoExtractor.get_chapters(video)
        assert len(chapters) == 2
        # "abc: Invalid [!]" is absorbed into first chapter's description
        assert chapters[0][0] == 0
        assert "Valid chapter" in chapters[0][1]
        assert chapters[1] == [120, "Also valid [!]"]
