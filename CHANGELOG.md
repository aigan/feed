# Changelog

All notable changes to this project are documented here, grouped by development phase.

## 2026-02-08 — Linting and tests

- Added linting configuration
- Added test scripts

## 2025-10-04 — Only show new videos in update output

- Filtered update output to only display newly discovered videos

## 2025-09-21 — Handle channels making all videos private

- Gracefully handle channels where all videos have been made private

## 2025-05-24 — Handle empty channels

- Gracefully handle channels with no uploads

## 2025-04-21 — Transcript support, LLM-based video extraction, and classification

- Added transcript downloading via `youtube-transcript-api`
- Added transcript formatting with heading detection and merging
- Added LLM-based video data extraction using OpenAI/LangChain
- Saving processed transcripts alongside video data
- Added LLM-based classification experiments

## 2025-03-25 — Channel mirroring with sync state tracking

- Mirror channel uploads (full and incremental)
- Track sync state per channel with `Channel.SyncState`

## 2025-03-09 — Video class, archive versioning, and schema migrations

- Added `Video` class with fetch, update, and local caching
- Archive versioning for video data (`v1.json`, `v2.json`, etc.)
- Channel upload processing using video cache
- Channel schema migration logic
- Refactored channel archiving

## 2025-03-02 — Core classes and safe property access

- Added `Channel`, `Subscription`, and `Playlist` classes
- `SafeNamespace` for transparent handling of missing properties (returns falsy `NoneObject` instead of raising)
- Moved bulk subscription updates into `Subscription` class
- Organized channel data into per-channel directories

## 2025-02-27 — Initial foundation

- YouTube Data API integration with OAuth2 authentication
- Subscription listing and data persistence
- `Rating` class for tracking likes and dislikes
- Change detection with DeepDiff and archiving of changed/removed data
