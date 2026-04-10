# CLAUDE.md

See [STYLE.md](STYLE.md) for coding style guide and post-implementation checklist.

## Interaction Rules

- A question is not a request. When the user asks "why is X?" or "should we do Y?", answer the question — do not take action. Only make changes when explicitly asked.

## Project Overview

YouTube data aggregation and analysis system. Tracks subscriptions, mirrors channel uploads, archives video metadata with version history, downloads transcripts, and runs LLM-based content analysis via OpenAI/LangChain.

## Environment

Python 3.13+ with direnv handling everything: venv activation, `PYTHONPATH=lib`, API keys, and all required env vars. OAuth token cached at `var/token.json`; first run triggers interactive browser auth flow.

## Development

**Use TDD:** Write or update tests first to define expected behavior, verify they fail, then implement. Run the full test suite before considering work done.

## Architecture Notes

These are non-obvious patterns not covered by STYLE.md:

- **`Context` singleton** (`lib/context.py`): All models use `Context.get().batch_time` to stamp `first_seen`, `last_updated`, and archive paths with a single coordinated UTC timestamp per batch run.

- **Channel schema migration**: `Channel` has a `SCHEMA_VERSION` constant. When loading from JSON, if the stored version is below current, `migrate()` runs a chain of versioned migration functions before use.

- **YouTube special playlist prefixes**: `LL` = Liked, `WL` = Watch Later, `HL` = History. These are YouTube internal playlist IDs, not documented in the API.
