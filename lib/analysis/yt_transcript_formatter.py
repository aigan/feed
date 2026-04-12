import re
import textwrap
from collections import namedtuple
from typing import List, Tuple

from analysis import Processor

Result = namedtuple('Result', ['text', 'did_work'])

Heading = Tuple[int, int, str]  # (seconds, level, title)


class YTTranscriptFormatter(Processor):
    CLEANUP_PROMPT_VERSION = 2    # bumped when CLEANUP_PROMPT changes
    HEADINGS_PROMPT_VERSION = 2   # bumped when HEADINGS_PROMPT changes
    RECONCILE_PROMPT_VERSION = 1  # bumped when RECONCILE_PROMPT or merge logic changes
    CHUNK_SIZE = 400              # Up to 42 tokens per row
    STEP_SIZE = 370

    SNAP_WINDOW = 30       # seconds — manual chapter snaps to LLM heading within this

    HEADINGS_SHORT_CUTOFF  = 600    # seconds — ≤10 min: only `##`
    HEADINGS_MEDIUM_CUTOFF = 3600   # seconds — ≤60 min: `##` + `###`

    CLEANUP_PROMPT = """
Process this transcript chunk. Improve readability. Remove stutters or filler words. Some words may
be wrong because they sound similar to the real ones. Use the context to figure out what was
actually said. Create complete sentences but don't change any words from the original. Group sentences in paragraphs.

Each paragraph must start with the timestamp (an integer in seconds), then a colon and a space, then the text. Do not use markdown or any extra commentary or tags.
Example:
123: Welcome to this new video.

{extra_instructions}

Transcript chunk:
{transcript_chunk}
    """

    HEADINGS_PROMPT = """
Read the full cleaned transcript below and produce a table of contents.

{level_instructions}

Mark ads, sponsor segments, promos, and housekeeping breaks with `AD` in the title (e.g. `## AD — sponsor`).

Do not over-segment. A long monologue on a single subject is one chapter, not five. Aim for breaks that a reader scanning the table of contents would actually want to click.

Each entry must start with an integer timestamp in seconds that matches an existing timestamp in the transcript, followed by a space, then the markdown heading. No other text, no commentary, no preamble.

Example output:
{example_output}

Transcript:
{transcript}
    """

    HEADINGS_LEVEL_INSTRUCTIONS_SHORT = (
        "This is a short video. Emit only top-level `##` chapter breaks at the "
        "genuine structural boundaries of the video — major topic shifts, mode "
        "changes (intro → main → outro). Do not use any sub-levels (`###` or "
        "deeper). It is fine to emit only one or two `##` lines if the video "
        "is essentially single-topic."
    )

    HEADINGS_EXAMPLE_SHORT = (
        "0 ## Introduction\n"
        "45 ## Main demo\n"
        "320 ## AD — sponsor\n"
        "360 ## Wrap-up"
    )

    HEADINGS_LEVEL_INSTRUCTIONS_MEDIUM = (
        "Pick top-level `##` chapter breaks at the genuine structural boundaries "
        "of the video — major topic shifts, new interview segments, new news "
        "items, mode changes (intro → main → outro). Do not break inside a "
        "single ongoing argument or explanation.\n\n"
        "Nest `###` subtopic lines under a `##` chapter only when the chapter "
        "is long enough that an extra level clearly helps the reader navigate. "
        "It is fine to emit zero `###` lines if the structure is flat. Do not "
        "use `####` or deeper."
    )

    HEADINGS_EXAMPLE_MEDIUM = (
        "0 ## Introduction\n"
        "185 ## Wayward Realms announcement\n"
        "620 ### Combat redesign\n"
        "1240 ## AD — sponsor"
    )

    HEADINGS_LEVEL_INSTRUCTIONS_LONG = (
        "Because this is a long video, use three semantic levels:\n"
        "- `##` marks **sections** — the biggest structural groupings, e.g. "
        "distinct interviews, major acts, or large topic clusters. Sections "
        "are coarse: most videos have only a handful.\n"
        "- `###` marks **chapters** inside a section — the normal unit a "
        "viewer would actually jump to. This is the level that matches "
        "creator-authored YouTube chapters.\n"
        "- `####` marks **subtopics** inside a chapter, used sparingly and "
        "only when the chapter is long enough that the extra level clearly "
        "helps navigation.\n\n"
        "Not every section needs chapters, and not every chapter needs "
        "subtopics. Flat output inside a section is fine. Do not use `#` or "
        "`#####` and deeper."
    )

    HEADINGS_EXAMPLE_LONG = (
        "0 ## Section 1 — Opening interview\n"
        "120 ### Guest introduction\n"
        "480 ### Career background\n"
        "900 #### Early projects\n"
        "1500 ## Section 2 — News roundup\n"
        "1620 ### Story A\n"
        "2100 ### Story B\n"
        "3600 ## AD — sponsor"
    )

    RECONCILE_PROMPT = """
The table of contents below was produced from a transcript. Some chapters from the YouTube video description could not be matched to any existing entry within 30 seconds. Integrate each unmatched chapter into the table of contents.

For each unmatched chapter:
- If the chapter clearly refers to the same topic as an existing entry, update that entry's title to the chapter's title and keep its timestamp.
- Otherwise, insert it as a new entry at the chapter's timestamp, choosing a heading level (`##`, `###`, ...) that is consistent with the surrounding structure.

Output the full updated table of contents in the same `<seconds> <#-marks> <title>` format, one entry per line, sorted by timestamp. No commentary, no preamble.

Existing table of contents:
{merged}

Unmatched chapters from the description (timestamp and title only — no level):
{unmatched}
    """

    # ------------------------------------------------------------------
    # Phase 1: cleanup → transcript.txt
    # ------------------------------------------------------------------

    @classmethod
    def get_transcript(cls, video, force=False):
        """
        Ensure and return the cleaned transcript (`processed/transcript.txt`).

        Dependencies: `transcript.json` (downloaded via `video.transcript()`)
        plus the per-chunk cleanup cache.
        """
        from youtube import TranscriptMeta, Video
        path = Video.get_processed_dir(video.video_id) / 'transcript.txt'
        active_dir = Video.get_active_dir(video.video_id)
        meta = TranscriptMeta(active_dir)

        stored_version = meta.get('cleanup_prompt_version')
        version_ok = stored_version == cls.CLEANUP_PROMPT_VERSION
        if path.exists() and not force and version_ok:
            return Result(text=path.read_text(), did_work=False)

        # Snapshot unavailability before we re-consult the source so we can
        # tell "already known unavailable" from "just discovered unavailable".
        had_marker = meta.is_unavailable and not force

        transcript = video.transcript(force=force)
        if transcript is None:
            print('[No transcript]')
            return Result(text='', did_work=not had_marker)

        regenerate = force or not version_ok
        chunks = []
        chunk_id = 0
        while True:
            chunk_text = cls.get_chunk(video, transcript, chunk_id, force=regenerate)
            if chunk_text is None:
                break
            chunks.append(chunk_text)
            chunk_id += 1

        merged = cls.merge_transcript_chunks(chunks)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(merged)
        meta.stamp_step('cleanup', cls.CLEANUP_PROMPT_VERSION)
        return Result(text=merged, did_work=True)

    @classmethod
    def extract_transcript_segment(cls, transcript, offset):
        result = ''
        end_index = min(offset + cls.CHUNK_SIZE, len(transcript['segments']))
        if offset >= end_index:
            return None
        for i in range(offset, end_index):
            segment = transcript['segments'][i]
            start = int(round(segment['start'], 0))
            result += f"{start}: {segment['text']}\n"
        return result

    @classmethod
    def is_last_chunk(cls, transcript, chunk_id):
        next_chunk_offset = (chunk_id + 1) * cls.CHUNK_SIZE
        return next_chunk_offset >= len(transcript['segments'])

    @classmethod
    def get_chunk(cls, video, transcript, chunk_id, force=False):
        chunk_file = cls.get_transcript_chunk_dir(video.video_id) / f'{chunk_id:03}.txt'
        if chunk_file.exists() and not force:
            return chunk_file.read_text()
        return cls.run_chunk(video, transcript, chunk_id)

    @classmethod
    def run_chunk(cls, video, transcript, chunk_id):
        offset = chunk_id * cls.STEP_SIZE
        chunk = cls.extract_transcript_segment(transcript, offset)
        if chunk is None:
            return None

        first_line = chunk.partition('\n')[0]
        print(f'Processing chunk {chunk_id}: {first_line}')

        instructions = ''
        is_last = cls.is_last_chunk(transcript, chunk_id)
        if chunk_id == 0:
            if is_last:
                instructions = 'This is the *whole* of the transcript'
            else:
                instructions = """
                This is the *beginning* of the transcript.
                Start new paragraphs naturally.
                Don't assume prior context.
                The end is probably incomplete.
                """
        else:
            previous_text = cls.get_chunk(video, transcript, chunk_id - 1)
            paragraphs = cls.get_last_paragraphs(previous_text)
            chunk_order = (
                'This is the *end* of the transcript.' if is_last else 'This is a middle chunk.'
            )

            instructions = f"""
            {chunk_order}
            The first lines will repeat the end of the previous chunk.
            Start the processing after the [START HERE] marker. Create a new version of the paragraph at this point, that will replace `paragraph -1`. But check the transcript of the previous chunk, the [START HERE] might be off by one or two lines. See the previous chunk for how to start the paragraph.

            Previous chunk:
            ## [Paragraph -2]
            {paragraphs[-2]}

            ## [Paragraph -1, probably incomplete]
            {paragraphs[-1]}
            """

            match = re.match(r'^(\d+):', paragraphs[-1])
            start_ts = int(match.group(1))
            chunk_lines = chunk.splitlines()
            for i, line in enumerate(chunk_lines):
                match = re.match(r'^(\d+):', line)
                if match and int(match.group(1)) >= start_ts:
                    chunk_lines.insert(i, '[START HERE]')
                    break
            chunk = '\n'.join(chunk_lines)

        instructions = textwrap.dedent(instructions)

        text = cls.ask_llm(
            cls.CLEANUP_PROMPT,
            {
                'transcript_chunk': chunk,
                'extra_instructions': instructions,
            },
            profile='cleanup',
        )

        chunk_dir = cls.get_transcript_chunk_dir(video.video_id)
        chunk_file = chunk_dir / f'{chunk_id:03}.txt'
        chunk_file.parent.mkdir(parents=True, exist_ok=True)
        chunk_file.write_text(text)
        return text

    @classmethod
    def get_transcript_chunk_dir(cls, video_id):
        from youtube import Video
        return Video.get_processed_dir(video_id) / 'transcript_chunks'

    @classmethod
    def get_last_paragraphs(cls, text: str, count: int = 2) -> List[str]:
        paras = [line for line in text.splitlines() if re.match(r'^\d+:\s', line)]
        return paras[-count:]

    @classmethod
    def extract_first_timestamp(cls, chunk):
        """Extract the first timestamp (as int) from a chunk."""
        for line in chunk.strip().split('\n'):
            if ':' in line and not line.startswith('##'):
                try:
                    return int(line.split(':', 1)[0].strip())
                except ValueError:
                    continue
        return None

    @classmethod
    def extract_timestamp_from_line(cls, line):
        """Extract timestamp from a single line, if present."""
        if ':' in line and not line.startswith('##'):
            try:
                return int(line.split(':', 1)[0].strip())
            except ValueError:
                pass
        return None

    @classmethod
    def merge_transcript_chunks(cls, chunks):
        """
        Merge transcript chunks by finding overlap points between consecutive chunks.
        Strips `^##` lines at the end so old cached chunks (from before the
        two-phase split) don't contaminate the cleaned output.
        """
        if not chunks:
            return ''
        if len(chunks) == 1:
            return cls._strip_heading_lines(chunks[0])

        result = []
        previous_chunk = chunks[0]

        for current_chunk in chunks[1:]:
            current_first_timestamp = cls.extract_first_timestamp(current_chunk)

            if current_first_timestamp is not None:
                previous_lines = previous_chunk.strip().split('\n')
                cut_index = next(
                    (
                        i
                        for i, line in enumerate(previous_lines)
                        if cls.extract_timestamp_from_line(line) is not None
                        and cls.extract_timestamp_from_line(line) >= current_first_timestamp
                    ),
                    len(previous_lines),
                )
                result.append('\n'.join(previous_lines[:cut_index]))
            else:
                result.append(previous_chunk)

            previous_chunk = current_chunk

        result.append(previous_chunk)
        merged = '\n'.join(filter(None, result))
        return cls._strip_heading_lines(merged)

    @classmethod
    def _strip_heading_lines(cls, text: str) -> str:
        return '\n'.join(line for line in text.split('\n') if not line.lstrip().startswith('##'))

    # ------------------------------------------------------------------
    # Phase 2: headings
    # ------------------------------------------------------------------

    @classmethod
    def get_headings(cls, video, force=False):
        """
        Ensure and return the heading list (`processed/headings.txt`).

        Dependency: the cleaned transcript (`transcript.txt`). This call
        resolves that dependency itself by invoking `get_transcript`, so
        callers that only want the headings don't have to sequence the two.
        """
        from youtube import TranscriptMeta, Video
        path = Video.get_processed_dir(video.video_id) / 'headings.txt'
        active_dir = Video.get_active_dir(video.video_id)
        meta = TranscriptMeta(active_dir)

        cache_valid = (
            path.exists()
            and not force
            and meta.get('headings_prompt_version') == cls.HEADINGS_PROMPT_VERSION
            and meta.get('reconcile_prompt_version') == cls.RECONCILE_PROMPT_VERSION
        )
        if cache_valid:
            return Result(text=path.read_text(), did_work=False)

        # Resolve dependency — cached if already produced this batch.
        transcript_result = cls.get_transcript(video)
        if not transcript_result.text.strip():
            # No transcript → no headings. Record the empty state so the
            # next call sees a matching version and short-circuits.
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('')
            cls._stamp_headings_versions(active_dir)
            return Result(text='', did_work=False)

        text = cls.run_cleanup_headings(video, transcript_result.text)
        return Result(text=text, did_work=True)

    @classmethod
    def run_cleanup_headings(cls, video, transcript_text: str):
        from analysis import YTAPIVideoExtractor
        from youtube import Video

        active_dir = Video.get_active_dir(video.video_id)
        headings_file = Video.get_processed_dir(video.video_id) / 'headings.txt'

        if not transcript_text.strip():
            headings_file.parent.mkdir(parents=True, exist_ok=True)
            headings_file.write_text('')
            cls._stamp_headings_versions(active_dir)
            print('[No transcript for headings]')
            return ''

        llm_headings = cls.get_llm_headings(video, transcript_text)
        description_timestamps = YTAPIVideoExtractor.get_description_timestamps(video) or []

        print(f'[debug headings] {video.video_id} description timestamps:')
        if description_timestamps:
            for off, title in description_timestamps:
                print(f'[debug headings]   {off:>5}s  {title}')
        else:
            print('[debug headings]   (none)')
        print(f'[debug headings] llm headings: {len(llm_headings)} entries')

        merged, unmatched = cls.post_hoc_merge(
            llm_headings,
            description_timestamps,
            duration_seconds=getattr(video, 'duration_seconds', 0) or None,
        )

        if unmatched:
            print(
                f'[headings] {len(unmatched)} unmatched manual chapter(s) '
                f'— running LLM reconciliation'
            )
            merged = cls.reconcile_with_llm(merged, unmatched)

        text = cls.format_headings(merged)
        headings_file.parent.mkdir(parents=True, exist_ok=True)
        headings_file.write_text(text + '\n')
        cls._stamp_headings_versions(active_dir)
        print(text)
        return text

    @classmethod
    def _stamp_headings_versions(cls, active_dir):
        """Stamp the merged-headings step. Reads meta fresh so any
        updates written by `get_llm_headings` (which uses its own
        TranscriptMeta instance) are preserved instead of overwritten."""
        from context import Context
        from youtube import TranscriptMeta
        meta = TranscriptMeta(active_dir)
        meta.update({
            'headings_prompt_version': cls.HEADINGS_PROMPT_VERSION,
            'headings_updated_at': Context.get().batch_time.isoformat(),
            'reconcile_prompt_version': cls.RECONCILE_PROMPT_VERSION,
        })

    @classmethod
    def get_llm_headings(cls, video, transcript_text: str, force=False) -> List[Heading]:
        """
        Ensure and return the raw LLM headings (`processed/headings_llm.txt`).

        The LLM-only half of headings processing — no manual chapter merging.
        Cached per-video and invalidated by HEADINGS_PROMPT_VERSION, mirroring
        the caching shape used by `get_transcript` / `get_chunk`.
        """
        from youtube import TranscriptMeta, Video
        path = Video.get_processed_dir(video.video_id) / 'headings_llm.txt'
        meta = TranscriptMeta(Video.get_active_dir(video.video_id))

        stored_version = meta.get('llm_headings_prompt_version')
        if path.exists() and not force and stored_version == cls.HEADINGS_PROMPT_VERSION:
            return cls.parse_headings(path.read_text())

        llm_headings = cls.run_headings(video, transcript_text)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(cls.format_headings(llm_headings) + '\n')
        meta.stamp_step('llm_headings', cls.HEADINGS_PROMPT_VERSION)
        return llm_headings

    @classmethod
    def build_headings_prompt(cls, duration_seconds) -> str:
        """Return the HEADINGS_PROMPT template filled with level-specific
        instructions for this video's duration. The `{transcript}`
        placeholder is left intact for `ask_llm` to substitute."""
        if duration_seconds and duration_seconds <= cls.HEADINGS_SHORT_CUTOFF:
            instructions = cls.HEADINGS_LEVEL_INSTRUCTIONS_SHORT
            example = cls.HEADINGS_EXAMPLE_SHORT
        elif duration_seconds and duration_seconds > cls.HEADINGS_MEDIUM_CUTOFF:
            instructions = cls.HEADINGS_LEVEL_INSTRUCTIONS_LONG
            example = cls.HEADINGS_EXAMPLE_LONG
        else:
            instructions = cls.HEADINGS_LEVEL_INSTRUCTIONS_MEDIUM
            example = cls.HEADINGS_EXAMPLE_MEDIUM
        return cls.HEADINGS_PROMPT.replace(
            '{level_instructions}', instructions
        ).replace('{example_output}', example)

    @classmethod
    def run_headings(cls, video, transcript_text: str) -> List[Heading]:
        """Single full-transcript LLM call returning (seconds, level, title) tuples."""
        prompt = cls.build_headings_prompt(getattr(video, 'duration_seconds', 0))
        response = cls.ask_llm(
            prompt,
            {'transcript': transcript_text},
            profile='headings',
        )
        return cls.parse_headings(response)

    @classmethod
    def parse_headings(cls, text: str) -> List[Heading]:
        """Parse `<seconds> #..###### Title` lines into tuples. Permissive on
        level so the parser recovers anything the LLM emits within the
        markdown range."""
        result = []
        for line in text.splitlines():
            match = re.match(r'^\s*(\d+)\s+(#{1,6})\s+(.+?)\s*$', line)
            if match:
                result.append((int(match.group(1)), len(match.group(2)), match.group(3)))
        return result

    @classmethod
    def format_headings(cls, headings: List[Heading]) -> str:
        return '\n'.join(f'{off} {"#" * level} {title}' for off, level, title in headings)

    @classmethod
    def post_hoc_merge(
        cls,
        llm_headings: List[Heading],
        manual_chapters: List[Tuple[int, str]],
        duration_seconds: int = None,
    ) -> Tuple[List[Heading], List[Tuple[int, str]]]:
        """
        Replace LLM headings with the closest manual chapter title within
        SNAP_WINDOW. When several LLM headings are eligible, prefer the
        one with the highest level (lowest level number — `##` over
        `###`); break ties by closest distance. The replaced LLM heading
        keeps its timestamp and level; only the title is swapped.

        Bookend rules anchor the table of contents to the natural ends
        of the video:
        - A manual chapter at offset 0 is always placed at exactly 0:00,
          even if the closest LLM heading is later. This guarantees the
          first entry of the table of contents is at the start of the
          video.
        - When `duration_seconds` is given, a manual chapter within
          SNAP_WINDOW of the video end is placed at exactly that
          timestamp. The level comes from the absorbed LLM heading
          (if any) or defaults to `##`.
        - Even without manual chapters, a final-pass anchor pulls the
          first heading to 0 if it sits inside SNAP_WINDOW of 0, and
          pushes the last heading to `duration_seconds` if it sits
          inside SNAP_WINDOW of the video end.

        Each LLM heading can absorb at most one manual chapter. Manual
        chapters with no eligible LLM heading inside SNAP_WINDOW are
        returned in `unmatched` for later LLM reconciliation.
        """
        result = list(llm_headings)
        consumed: set = set()
        unmatched: List[Tuple[int, str]] = []
        bookend_handled: set = set()

        # Start bookend: first manual chapter at offset 0.
        for m_idx, (m_off, m_title) in enumerate(manual_chapters):
            if m_off == 0:
                cls._place_bookend(result, consumed, 0, m_title)
                bookend_handled.add(m_idx)
                break

        # End bookend: last manual chapter within SNAP_WINDOW of the
        # video end. Walk in reverse so we pick the trailing one when
        # multiple chapters cluster near the end.
        if duration_seconds:
            for m_idx in range(len(manual_chapters) - 1, -1, -1):
                if m_idx in bookend_handled:
                    continue
                m_off, m_title = manual_chapters[m_idx]
                if abs(m_off - duration_seconds) <= cls.SNAP_WINDOW:
                    cls._place_bookend(result, consumed, duration_seconds, m_title)
                    bookend_handled.add(m_idx)
                    break

        for m_idx, (m_off, m_title) in enumerate(manual_chapters):
            if m_idx in bookend_handled:
                continue

            best_idx = None
            best_key = None  # (level_asc, distance_asc)
            for i, (off, level, _title) in enumerate(result):
                if i in consumed:
                    continue
                dist = abs(off - m_off)
                if dist > cls.SNAP_WINDOW:
                    continue
                key = (level, dist)
                if best_key is None or key < best_key:
                    best_idx = i
                    best_key = key

            if best_idx is None:
                print(
                    f'[debug merge] unmatched manual {m_off}s "{m_title}" '
                    f'(no llm heading within {cls.SNAP_WINDOW}s)'
                )
                unmatched.append((m_off, m_title))
                continue

            off, level, old_title = result[best_idx]
            print(
                f'[debug merge] snap manual {m_off}s "{m_title}" -> '
                f'llm {off}s level={level} "{old_title}" (dist={best_key[1]}s)'
            )
            result[best_idx] = (off, level, m_title)
            consumed.add(best_idx)

        result.sort(key=lambda x: x[0])
        cls._anchor_bookends(result, duration_seconds)
        return result, unmatched

    @classmethod
    def _anchor_bookends(
        cls,
        result: List[Heading],
        duration_seconds: int = None,
    ) -> None:
        """Pull the first heading to 0 and push the last heading to
        `duration_seconds` when each is within SNAP_WINDOW of its
        natural anchor. Mutates `result` in place. With a single
        heading, only the start anchor is applied so a tiny video
        doesn't end up with its only entry pushed to the very end."""
        if not result:
            return

        first_off, first_level, first_title = result[0]
        if 0 < first_off <= cls.SNAP_WINDOW:
            print(
                f'[debug merge] anchor first heading {first_off}s -> 0 '
                f'"{first_title}"'
            )
            result[0] = (0, first_level, first_title)

        if duration_seconds and len(result) > 1:
            last_off, last_level, last_title = result[-1]
            gap = duration_seconds - last_off
            if 0 < gap <= cls.SNAP_WINDOW:
                print(
                    f'[debug merge] anchor last heading {last_off}s -> '
                    f'{duration_seconds} "{last_title}"'
                )
                result[-1] = (duration_seconds, last_level, last_title)

    @classmethod
    def _place_bookend(
        cls,
        result: List[Heading],
        consumed: set,
        target_off: int,
        m_title: str,
    ) -> None:
        """Force a manual chapter onto `target_off`, absorbing the
        closest non-consumed LLM heading within SNAP_WINDOW (adopting
        its level) or appending a new `##` entry. Mutates `result`
        and `consumed` in place."""
        best_idx = None
        best_dist = cls.SNAP_WINDOW + 1
        for j, (off, _level, _title) in enumerate(result):
            if j in consumed:
                continue
            dist = abs(off - target_off)
            if dist <= cls.SNAP_WINDOW and dist < best_dist:
                best_idx = j
                best_dist = dist
        if best_idx is not None:
            _off, level, old_title = result[best_idx]
            print(
                f'[debug merge] bookend {target_off}s "{m_title}" -> '
                f'llm {_off}s level={level} "{old_title}" (dist={best_dist}s)'
            )
            result[best_idx] = (target_off, level, m_title)
            consumed.add(best_idx)
        else:
            print(
                f'[debug merge] bookend {target_off}s "{m_title}" '
                f'(no llm heading within {cls.SNAP_WINDOW}s — new ##)'
            )
            result.append((target_off, 2, m_title))

    @classmethod
    def reconcile_with_llm(
        cls,
        merged_headings: List[Heading],
        unmatched_chapters: List[Tuple[int, str]],
    ) -> List[Heading]:
        """
        Single LLM call that integrates manual chapters which could not be
        snapped deterministically. The LLM receives the current merged
        table of contents and the unmatched manual chapters, and returns
        the full updated table of contents.
        """
        merged_text = cls.format_headings(merged_headings)
        unmatched_text = '\n'.join(
            f'{off} {title}' for off, title in unmatched_chapters
        )
        response = cls.ask_llm(
            cls.RECONCILE_PROMPT,
            {'merged': merged_text, 'unmatched': unmatched_text},
            profile='headings',
        )
        return cls.parse_headings(response)

    # ------------------------------------------------------------------
    # On-demand merge — combine the two files for consumers that want
    # headings inline with the transcript. No extra file on disk.
    # ------------------------------------------------------------------

    @classmethod
    def get_transcript_with_headers(cls, video):
        """
        Yield merged transcript + heading lines in timestamp order.

        The two artifacts live on disk as separate files (`transcript.txt`
        and `headings.txt`); this helper merges them in memory for any
        consumer that wants the combined reader-view.
        """
        transcript_text = cls.get_transcript(video).text
        if not transcript_text:
            return
        headings_text = cls.get_headings(video).text
        yield from cls._iter_merged_lines(transcript_text, headings_text)

    @classmethod
    def _iter_merged_lines(cls, transcript_text: str, headings_text: str):
        """Generate merged lines from two text blobs in timestamp order.

        Shared merge logic for both `get_transcript_with_headers` (iterator
        form) and `insert_headings_in_transcript` (string form, kept as a
        convenience for callers that want the full blob).
        """
        timestamps = [
            (int(m.group(1)), 1, m.group(0))
            for m in re.finditer(r'^(\d+): (.+)$', transcript_text, re.MULTILINE)
        ]
        headings = [
            (int(m.group(1)), 0, m.group(2))
            for m in re.finditer(r'^(\d+) (#.+)$', headings_text, re.MULTILINE)
        ]
        merged = timestamps + headings
        merged.sort(key=lambda x: (x[0], x[1]))
        for _key, _prio, line in merged:
            yield line

    @classmethod
    def insert_headings_in_transcript(cls, transcript_text: str, headings_text: str):
        """Return the merged transcript+headings text as a single string."""
        return ''.join(
            f'{line}\n\n'
            for line in cls._iter_merged_lines(transcript_text, headings_text)
        )
