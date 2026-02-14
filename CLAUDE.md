# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

See [STYLE.md](STYLE.md) for coding style guide and post-implementation checklist.

## Interaction Rules

- A question is not a request. When the user asks "why is X?" or "should we do Y?", answer the question — do not take action. Only make changes when explicitly asked.

## Project Overview

YouTube data aggregation and analysis system. Tracks subscriptions, mirrors channel uploads, archives video metadata with version history, downloads transcripts, and runs LLM-based content analysis via OpenAI/LangChain.

## Environment Setup

- **Python 3.13+** with virtualenv in `.venv/`
- Uses **direnv** (`.envrc`) to activate venv, set `PYTHONPATH=lib`, and configure API keys
- Required env vars: `PROJECT_ROOT`, `GOOGLE_OAUTH_FILE`, `CHROME_USER_DIR`, `CHROME_PROFILE`, `OPENAI_API_KEY`
- OAuth token cached at `var/token.json`; first run triggers interactive browser auth flow
- Install deps: `pip install -r requirements.txt`

## Running Scripts

All executable scripts are in `bin/youtube/` and `bin/web/`. Run from project root with direnv active:

```bash
python bin/youtube/update_videos.py      # Sync uploads from all subscriptions
python bin/youtube/update_likes.py       # Sync liked videos
python bin/youtube/update_dislikes.py    # Sync disliked videos
python bin/youtube/analyze_video.py      # LLM analysis of a video
python bin/youtube/update_all_subscriptions.py  # Sync subscription list
python bin/youtube/mirror_channels.py    # Mirror channel uploads
```

There is no test framework, build system, or linter configured. Ad-hoc test scripts exist (e.g., `bin/youtube/test.py`, `bin/web/transcript_test.py`).

## Architecture

### Library modules (`lib/`)

- **`youtube/`** — Package wrapping YouTube Data API v3:
  - `client.py` — OAuth2 authentication, builds `googleapiclient` service object
  - `video.py` — `Video` dataclass: fetch, update, archive, transcript download
  - `channel.py` — `Channel` dataclass: metadata, upload mirroring (full + incremental), sync state, schema migrations
  - `subscription.py` — `Subscription`: streams active subscriptions from API
  - `ratings.py` — `Rating`: likes/dislikes tracking
  - `playlist.py` — `Playlist` management
  - `transcript.py` — `Transcript`: downloads via `youtube-transcript-api`
  - `__init__.py` — Re-exports all classes plus `get_youtube_client` and `HttpError`

- **`analysis/`** — LLM-powered content analysis:
  - `processor.py` — `Processor` base class: `ask_llm()` wraps LangChain ChatOpenAI (default model: `gpt-4.1-mini`)
  - `ytapi_video_extractor.py` — Extracts metadata using GPT
  - `yt_transcript_formatter.py` — Formats transcripts for LLM prompting

- **`config.py`** — Reads `PROJECT_ROOT` and Chrome config from env vars, exports `ROOT` as `Path`
- **`context.py`** — `Context` singleton holding `batch_time` (UTC) for coordinated updates
- **`util.py`** — Core utilities:
  - `SafeNamespace`/`NoneObject` — Dot-access dicts with safe missing-attribute handling (returns falsy `NoneObject` instead of raising)
  - `to_obj()`/`from_obj()` — Convert between dicts and `SafeNamespace`
  - `convert_fields()` — Type-coerce dict values to match dataclass field annotations (datetime, int, bool)
  - `to_serializable()` — Dataclass → JSON-safe dict
  - `dump_json()` — Write JSON to file, auto-creating parent dirs

### Data flow pattern

1. API data is fetched via `retrieve()` class methods → raw dict
2. `update()` compares new data against existing JSON via **DeepDiff**, archives old version if changed
3. `get()` loads from local JSON, falling back to `update()` if missing
4. All timestamps coordinated through `Context.get().batch_time`

### Data storage (`data/youtube/`)

- **`active/`** — Current state as JSON files
  - Videos: `videos/active/{id[:2]}/{id}/video.json` (sharded by 2-char prefix)
  - Channels: `channels/active/{channel_id}/channel.json`
  - Uploads: `channels/active/{channel_id}/uploads/{year}.json` (list of `[video_id, published_at]` tuples)
  - Transcripts: `videos/active/{id[:2]}/{id}/transcript.json`
- **`archive/`** — Historical snapshots
  - Channels: archived by `{year}/week-{NN}/{channel_id}/`
  - Videos: versioned as `v1.json`, `v2.json`, etc.

### Key conventions

- Scripts in `bin/` must be executable (`chmod +x`)

- Imports use package names directly (`from youtube import Video`, `from config import ROOT`) — works because `PYTHONPATH` includes `lib/`
- Dataclass models use `@dataclass` with typed fields; constructed via `cls(**convert_fields(cls, data))`
- `SafeNamespace` wraps API responses so missing fields return `NoneObject` (falsy) instead of raising `AttributeError`
- Channel schema has versioning (`SCHEMA_VERSION`) with migration functions
- YouTube special playlist IDs: LL = Liked, WL = Watch Later, HL = History
