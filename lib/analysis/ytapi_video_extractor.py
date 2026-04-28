import re

from analysis import Processor
from context import Context


class YTAPIVideoExtractor(Processor):
    PROMPT_VERSION = 4

    TRACE_FORMATS = {'news', 'commentary', 'reaction', 'embed'}
    ENTITY_CATEGORIES = {
        'person', 'organization', 'product', 'workseries',
        'technology', 'location', 'date', 'event',
    }
    KNOWN_SECTIONS = frozenset({
        'FORMAT', 'EPISODE', 'SPEAKERS', 'ENTITIES',
        'CONCEPTS', 'RELATIONSHIPS', 'SOURCES',
    })

    # TODO(comments-to-llm): consume comment_selector output. Decide:
    # - which classes feed in (must-read always; quality subject to budget).
    # - thread formatting (parent + selected replies) vs flat.
    # - token budget per video.
    # - which existing sections gain a [from comments] provenance marker.

    @classmethod
    def get(cls, video):
        import json

        from youtube import Video

        video_id = video.video_id
        result_file = Video.get_processed_dir(video_id) / 'ytapi_extracted.json'
        if result_file.exists():
            result = json.loads(result_file.read_text())
            if (result['prompt_version'] == cls.PROMPT_VERSION and
                result['video_last_updated'] == video.last_updated.isoformat()):
                return result
        return cls.run(video)

    @classmethod
    def run(cls, video):
        from util import dump_json
        from youtube import Video

        video_id = video.video_id
        result_file = Video.get_processed_dir(video_id) / 'ytapi_extracted.json'

        context = cls._build_context(video)

        print('  [1/3] Extracting...')
        extracted = cls._step_extract(context)

        source_trace = None
        if cls._should_trace(extracted):
            print('  [2/3] Tracing source...')
            source_trace = cls._step_source_trace(context, extracted)
        else:
            print('  [2/3] Source trace: skipped')

        print('  [3/3] Evaluating...')
        evaluation, evaluation_raw = cls._step_evaluate(context, extracted, source_trace)

        result = cls._assemble(video, context, extracted, source_trace, evaluation)
        cls._validate(result, context)
        dump_json(result_file, result)
        raw_file = result_file.with_name('ytapi_extracted.txt')
        raw_file.write_text(extracted.get('_raw', ''))
        eval_raw_file = result_file.with_name('ytapi_extracted_evaluation.txt')
        eval_raw_file.write_text(evaluation_raw)
        return result

    # --- Input preparation ---

    @classmethod
    def _build_context(cls, video):
        from analysis.description_filter import DescriptionFilter

        channel = video.channel
        description = DescriptionFilter.strip(video.description, video, video.channel_id)
        unique_length = DescriptionFilter.unique_length(video.description, video.channel_id)
        tags = DescriptionFilter.clean_tags(video.tags, channel.title)

        # Chapters are extracted mechanically from the raw description so
        # that bracketed formats like `[00:00] Intro` survive DescriptionFilter.
        description_timestamps = cls.extract_description_timestamps(video.description)

        categories = []
        if video.topic_details and 'topicCategories' in video.topic_details:
            for url in video.topic_details['topicCategories']:
                name = url.rsplit('/', 1)[-1].replace('_', ' ')
                categories.append(name)

        return {
            'title': video.title,
            'channel_title': channel.title,
            'description': description,
            'unique_length': unique_length,
            'date': video.published_at,
            'length': video.duration_formatted,
            'duration_seconds': video.duration_seconds,
            'tags': tags,
            'categories': categories,
            'description_timestamps': description_timestamps,
        }

    @classmethod
    def extract_description_timestamps(cls, description):
        """Parse (offset, title) chapter markers straight from a video
        description. Mechanical; no LLM, no cached JSON — the single source
        of truth for description-derived timestamps."""
        from youtube import Transcript

        processed = Transcript.process_timestamps(description)
        pattern = re.compile(r'\[ts (\d+)\]\s+\d+:(?:\d+:)?\d+\s*(.*)')
        result = []
        for match in pattern.finditer(processed):
            offset = int(match.group(1))
            text = match.group(2).strip()
            if text:
                result.append({'offset': offset, 'description': text})
        return result

    # --- Parsing helpers ---

    @classmethod
    def _parse_sections(cls, text):
        """Split LLM output into sections.

        Primary format is `=== SECTION ===`. Also accepts `## SECTION` /
        `### SECTION` and bare `SECTION:` when the token matches a known
        section name, so drift from bigger models (markdown fence wrapping,
        heading-style delimiters) doesn't silently drop content.
        """
        sections = {}
        current = None
        lines = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith('```'):
                continue
            name = cls._match_section_header(line)
            if name is not None:
                if current is not None:
                    sections[current] = '\n'.join(lines).strip()
                current = name
                lines = []
            else:
                lines.append(raw_line)
        if current is not None:
            sections[current] = '\n'.join(lines).strip()
        return sections

    _SECTION_HEADER_RE = re.compile(
        r'^(?:===\s*(?P<fenced>.+?)\s*==='
        r'|#{2,6}\s*(?P<heading>[A-Z][A-Z_ ]*?)\s*:?'
        r'|(?P<colon>[A-Z][A-Z_ ]*?):)$'
    )

    @classmethod
    def _match_section_header(cls, line):
        match = cls._SECTION_HEADER_RE.match(line)
        if not match:
            return None
        token = match.group('fenced') or match.group('heading') or match.group('colon')
        name = token.strip().upper().replace(' ', '_')
        if match.group('fenced'):
            return name
        return name if name in cls.KNOWN_SECTIONS else None

    @classmethod
    def _parse_pipe_lines(cls, text):
        """Split non-empty lines by ' | ', return list of tuples."""
        result = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = [p.strip() for p in line.split(' | ')]
            result.append(parts)
        return result

    @classmethod
    def _parse_pipe_section(cls, sections, key, fields):
        """Parse a pipe-delimited section into a list of dicts with given field names."""
        result = []
        if key in sections:
            for parts in cls._parse_pipe_lines(sections[key]):
                entry = {name: parts[i] if len(parts) > i else ''
                         for i, name in enumerate(fields)}
                result.append(entry)
        return result

    @classmethod
    def _parse_prefixed(cls, text):
        """Parse PREFIX: value lines into a dict."""
        result = {}
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            match = re.match(r'^([A-Z_]+):\s*(.*)', line)
            if match:
                result[match.group(1).lower()] = match.group(2).strip()
        return result

    # --- Step 1: Extract ---

    _EXTRACT_SECTIONS = [
        ('FORMAT', (
            '# Video format:\n'
            '<FORMAT>one or more of: interview, discussion, monologue, presentation, '
            'documentary, essay, review, reaction, commentary, embed, letsplay, '
            'news, tutorial, vlog, compilation, livestream, skit, other</FORMAT>\n'
            '<EXAMPLE>\ndiscussion\npresentation\n</EXAMPLE>\n'
            'Video format:'
        )),
        ('EPISODE', (
            '# Episode:\n'
            '<FORMAT>series title | episode number or name (or "none")</FORMAT>\n'
            '<EXAMPLE>\nThe Daily Show | Episode 42 - Guest Special\n</EXAMPLE>\n'
            'Episode:'
        )),
        ('SPEAKERS', (
            '# All speakers:\n'
            '<FORMAT>full name | role (host/guest/narrator/subject/referenced) '
            '| short description</FORMAT>\n'
            '<EXAMPLE>\nAdam Berg | guest | topic expert\n'
            'Cecil Dalton | host | -\n</EXAMPLE>\n'
            'All speakers:'
        )),
        ('ENTITIES', (
            '# All named entities (include speakers above):\n'
            '<FORMAT>canonical name | category (person/organization/product/'
            'workseries/technology/location/date/event) | aliases if any</FORMAT>\n'
            '<EXAMPLE>\nAdam Berg | person | -\n'
            'TechCorp | organization | Tech Corp, TC\n'
            'Quantum Engine | technology | QE\n</EXAMPLE>\n'
            'All named entities:'
        )),
        ('CONCEPTS', (
            '# Key ideas and topics:\n'
            '<FORMAT>keyword | description of its context in this video</FORMAT>\n'
            '<EXAMPLE>\nmachine learning | discussed as the main driver behind '
            "the product's recommendation system\n"
            'open source | contrasted with proprietary approaches to AI '
            'development\n</EXAMPLE>\n'
            'Key ideas and topics:'
        )),
        ('RELATIONSHIPS', (
            '# Important connections between entities or concepts:\n'
            '<FORMAT>entity1 + entity2 | relationship description</FORMAT>\n'
            '<EXAMPLE>\nAdam Berg + TechCorp | founder and CEO\n'
            'Quantum Engine + machine learning | engine uses ML for '
            'optimization\n</EXAMPLE>\n'
            'Important connections:'
        )),
        ('SOURCES', (
            '# External items the video cites, reacts to, or is based on:\n'
            '<FORMAT>source description | identifying clues (speaker, title, '
            'date, platform) | URL or none</FORMAT>\n'
            '<EXAMPLE>\nNature paper on quantum computing | Smith et al., 2024, '
            'Nature | https://doi.org/example\n'
            'Industry report | mentioned by host, no title given | none\n'
            '</EXAMPLE>\n'
            'If there are no external sources, write exactly: none\n'
            'External sources:'
        )),
    ]

    @classmethod
    def _step_extract(cls, context):
        description_note = ''
        if context['unique_length'] < 50:
            description_note = (
                '\nNote: Description is minimal. '
                'Extract from title and tags only.\n'
            )

        tags = ', '.join(context['tags']) if context['tags'] else 'None'
        categories = ', '.join(context['categories']) if context['categories'] else 'None'

        system_prompt = (
            'VIDEO METADATA EXTRACTION\n\n'
            'Extract structured information from the video metadata below.\n'
            'Focus on facts only — no confidence ratings, no quality judgments, '
            'no timestamps.\n'
            f'{description_note}'
            'Use ` | ` (space-pipe-space) to separate fields. One entry per line.\n'
            'Do not wrap output in markdown code fences.\n\n'
            f'Video Title: {context["title"]}\n'
            f'Channel: {context["channel_title"]}\n'
            f'Upload date: {context["date"]}\n'
            f'Length: {context["length"]}\n'
            f'Description:\n{context["description"]}\n'
            f'Tags: {tags}\n'
            f'Categories: {categories}'
        )

        conv = cls.conversation(profile='extract')
        conv.system(system_prompt)

        raw_parts = []
        responses = {}
        for name, prompt in cls._EXTRACT_SECTIONS:
            text = conv.ask(prompt)
            responses[name] = text
            raw_parts.append(f'=== {name} ===\n{text}')

        extracted = cls._parse_section_responses(responses)
        extracted['_raw'] = '\n\n'.join(raw_parts) + '\n'
        return extracted

    @classmethod
    def _parse_section_responses(cls, responses):
        formats = []
        for line in responses.get('FORMAT', '').splitlines():
            line = line.strip().lower()
            if line:
                formats.append(line)

        episode = None
        ep_text = responses.get('EPISODE', '').strip()
        if ep_text.lower() != 'none' and ep_text:
            parts = [p.strip() for p in ep_text.split(' | ')]
            episode = {
                'series': parts[0],
                'episode': parts[1] if len(parts) > 1 else None,
            }

        speakers = cls._parse_pipe_section_from_text(
            responses.get('SPEAKERS', ''), ('name', 'role', 'description'))
        entities = cls._parse_pipe_section_from_text(
            responses.get('ENTITIES', ''), ('name', 'category', 'aliases'))
        for e in entities:
            e['category'] = e['category'].strip(' |')
        concepts = cls._parse_pipe_section_from_text(
            responses.get('CONCEPTS', ''), ('keyword', 'description'))
        relationships = cls._parse_pipe_section_from_text(
            responses.get('RELATIONSHIPS', ''), ('entities', 'description'))
        sources = cls._parse_pipe_section_from_text(
            responses.get('SOURCES', ''), ('description', 'clues', 'url'))
        for s in sources:
            if not s['url'] or s['url'].lower() == 'none':
                s['url'] = None
        sources = [s for s in sources if s['description'].lower() not in ('none', 'n/a', '-')]

        return {
            'formats': formats,
            'episode': episode,
            'speakers': speakers,
            'entities': entities,
            'concepts': concepts,
            'relationships': relationships,
            'sources': sources,
        }

    @classmethod
    def _parse_pipe_section_from_text(cls, text, fields):
        result = []
        for parts in cls._parse_pipe_lines(text):
            entry = {name: parts[i] if len(parts) > i else ''
                     for i, name in enumerate(fields)}
            result.append(entry)
        return result

    @classmethod
    def _parse_extraction(cls, text):
        sections = cls._parse_sections(text)
        if not (sections.keys() & cls.KNOWN_SECTIONS):
            snippet = text[:500].replace('\n', ' ⏎ ')
            print(f'  [warn] extract output had no recognizable sections: {snippet!r}')

        formats = []
        if 'FORMAT' in sections:
            for line in sections['FORMAT'].splitlines():
                line = line.strip().lower()
                if line:
                    formats.append(line)

        episode = None
        if 'EPISODE' in sections:
            ep_text = sections['EPISODE'].strip()
            if ep_text.lower() != 'none' and ep_text:
                parts = [p.strip() for p in ep_text.split(' | ')]
                episode = {
                    'series': parts[0],
                    'episode': parts[1] if len(parts) > 1 else None,
                }

        speakers = cls._parse_pipe_section(sections, 'SPEAKERS', ('name', 'role', 'description'))
        entities = cls._parse_pipe_section(sections, 'ENTITIES', ('name', 'category', 'aliases'))
        concepts = cls._parse_pipe_section(sections, 'CONCEPTS', ('keyword', 'description'))
        relationships = cls._parse_pipe_section(sections, 'RELATIONSHIPS', ('entities', 'description'))
        sources = cls._parse_pipe_section(sections, 'SOURCES', ('description', 'clues', 'url'))
        for s in sources:
            if not s['url'] or s['url'].lower() == 'none':
                s['url'] = None
        sources = [s for s in sources if s['description'].lower() not in ('none', 'n/a', '-')]

        return {
            'formats': formats,
            'episode': episode,
            'speakers': speakers,
            'entities': entities,
            'concepts': concepts,
            'relationships': relationships,
            'sources': sources,
        }

    # --- Step 2: Source trace ---

    @classmethod
    def _should_trace(cls, extracted):
        if set(extracted['formats']) & cls.TRACE_FORMATS:
            return True
        if extracted['sources'] and all(s['url'] is None for s in extracted['sources']):
            return True
        return False

    @classmethod
    def _step_source_trace(cls, context, extracted):
        entities_text = '\n'.join(
            f"  {e['name']} ({e['category']})" for e in extracted['entities']
        )
        sources_text = '\n'.join(
            f"  {s['description']} ({s['clues']})" for s in extracted['sources']
        )

        prompt = """ORIGINAL SOURCE IDENTIFICATION

This video appears to be secondary coverage. Identify what original material it covers.

Video Title: {title}
Channel: {channel_title}
Description:
{description}

Extracted entities:
{entities}

Extracted sources:
{sources}

Identify the original material being covered. Output exactly these fields:
ORIGINAL: what the video is covering (concise label)
CREATOR: who created the original material
TYPE: announcement / article / video / paper / event / product / other
CLUES: evidence for or against this being identifiable (language, missing links, speculative phrasing)
URL: URL if found, otherwise none"""

        text = cls.ask_llm(
            prompt,
            {
                'title': context['title'],
                'channel_title': context['channel_title'],
                'description': context['description'],
                'entities': entities_text or '  (none)',
                'sources': sources_text or '  (none)',
            },
            profile='extract',
        )

        parsed = cls._parse_prefixed(text)
        url = parsed.get('url')
        if url and url.lower() == 'none':
            url = None
        return {
            'original': parsed.get('original', ''),
            'creator': parsed.get('creator', ''),
            'type': parsed.get('type', ''),
            'clues': parsed.get('clues', ''),
            'url': url,
        }

    # --- Step 3: Evaluate ---

    @classmethod
    def _step_evaluate(cls, context, extracted, source_trace):
        formats_text = ', '.join(extracted['formats'])
        speakers_text = '\n'.join(
            f"  {s['name']} ({s['role']})" for s in extracted['speakers']
        )
        entities_text = '\n'.join(
            f"  {e['name']} ({e['category']})" for e in extracted['entities']
        )
        concepts_text = '\n'.join(
            f"  {c['keyword']}" for c in extracted['concepts']
        )

        trace_text = 'not performed'
        if source_trace:
            trace_text = (
                f"{source_trace['original']} by {source_trace['creator']}"
                f" ({source_trace['type']})"
            )

        prompt = """Review this video metadata extraction. Assess how much we can actually determine from the available metadata.

Original metadata:
Title: {title}
Description length: {unique_length} unique characters
Video length: {length}

Extraction summary:
Formats: {formats}
Speakers:
{speakers}
Entities:
{entities}
Key concepts:
{concepts}

Source trace: {source_trace}

Assess each of these — use the exact prefix labels:

COVERAGE: How much of the video content can we infer from metadata? (full / partial / minimal)

GAPS: What important things can we NOT determine from metadata alone? List specific unknowns, one per line starting with "- ".

SUPPORTED: Which extracted items are directly supported by the description? Which are inferred? One per line starting with "- ".

VALUE: Can you estimate quality scores from this metadata?
If yes, output on separate lines: insight: N, novelty: N, quality: N, delivery: N (each 1-5).
If not enough information, write: insufficient metadata

VERDICT: One of:
- discard: clearly not worth pursuing (spam, duplicate, off-topic)
- score: enough metadata to assign meaningful quality scores
- need_transcript: can't reliably judge quality from metadata alone"""

        text = cls.ask_llm(
            prompt,
            {
                'title': context['title'],
                'unique_length': context['unique_length'],
                'length': context['length'],
                'formats': formats_text or 'unknown',
                'speakers': speakers_text or '  (none)',
                'entities': entities_text or '  (none)',
                'concepts': concepts_text or '  (none)',
                'source_trace': trace_text,
            },
            profile='extract',
        )

        return cls._parse_evaluation(text), text

    @classmethod
    def _parse_evaluation(cls, text):
        # Split into sections by prefix labels
        sections = {}
        current_key = None
        current_lines = []
        for line in text.splitlines():
            match = re.match(
                r'^(COVERAGE|GAPS|SUPPORTED|VALUE|VERDICT):\s*(.*)', line
            )
            if match:
                if current_key:
                    sections[current_key] = '\n'.join(current_lines).strip()
                current_key = match.group(1).lower()
                current_lines = [match.group(2)]
            else:
                current_lines.append(line)
        if current_key:
            sections[current_key] = '\n'.join(current_lines).strip()

        coverage = sections.get('coverage', 'minimal').strip().lower()
        if coverage not in ('full', 'partial', 'minimal'):
            coverage = 'minimal'

        gaps = []
        for line in sections.get('gaps', '').splitlines():
            line = line.strip()
            if line.startswith('- '):
                gaps.append(line[2:].strip())
            elif line:
                gaps.append(line)

        supported = []
        for line in sections.get('supported', '').splitlines():
            line = line.strip()
            if line.startswith('- '):
                supported.append(line[2:].strip())
            elif line:
                supported.append(line)

        value = None
        value_text = sections.get('value', '')
        if 'insufficient' not in value_text.lower():
            scores = {}
            for key in ('insight', 'novelty', 'quality', 'delivery'):
                score_match = re.search(
                    rf'{key}:\s*(\d)', value_text, re.IGNORECASE
                )
                if score_match:
                    scores[key] = int(score_match.group(1))
            if scores:
                value = scores

        verdict = sections.get('verdict', 'need_transcript').strip().lower()
        for v in ('discard', 'score', 'need_transcript'):
            if v in verdict:
                verdict = v
                break
        else:
            verdict = 'need_transcript'

        return {
            'coverage': coverage,
            'gaps': gaps,
            'supported': supported,
            'value': value,
            'verdict': verdict,
        }

    # --- Assembly, validation, output ---

    @classmethod
    def _format_text(cls, extracted, description_timestamps):
        """Generate backward-compatible text representation."""
        lines = []

        lines.append('FORMAT:')
        for f in extracted['formats']:
            lines.append(f)
        lines.append('')

        lines.append('EPISODE:')
        if extracted['episode']:
            ep = extracted['episode']
            lines.append(f"{ep['series']}: {ep['episode'] or ''}")
        else:
            lines.append('none')
        lines.append('')

        lines.append('SPEAKERS:')
        for s in extracted['speakers']:
            lines.append(f"{s['name']} | {s['role']} | {s['description']}")
        lines.append('')

        lines.append('DESCRIPTION TIMESTAMPS:')
        for ts in description_timestamps:
            lines.append(f"{ts['offset']}: {ts['description']}")
        lines.append('')

        lines.append('ENTITIES:')
        for e in extracted['entities']:
            lines.append(f"{e['name']} | {e['category']} | {e['aliases']}")
        lines.append('')

        lines.append('CONCEPTS:')
        for c in extracted['concepts']:
            lines.append(f"{c['keyword']} | {c['description']}")
        lines.append('')

        lines.append('RELATIONSHIPS:')
        for r in extracted['relationships']:
            lines.append(f"{r['entities']} | {r['description']}")
        lines.append('')

        lines.append('SOURCES:')
        for s in extracted['sources']:
            lines.append(f"{s['description']} | {s['clues']} | {s['url'] or 'none'}")

        return '\n'.join(lines)

    @classmethod
    def _validate(cls, result, context):
        entity_names = {e['name'].lower() for e in result.get('entities', [])}
        for speaker in result.get('speakers', []):
            if speaker['name'].lower() not in entity_names:
                print(f"  [warn] Speaker '{speaker['name']}' not found in entities")

        for entity in result.get('entities', []):
            if entity['category'].lower() not in cls.ENTITY_CATEGORIES:
                print(f"  [warn] Entity '{entity['name']}' has unknown category '{entity['category']}'")

        if result.get('evaluation', {}).get('value'):
            for key, score in result['evaluation']['value'].items():
                if not (1 <= score <= 5):
                    print(f"  [warn] Value score '{key}' is {score}, expected 1-5")

        description_timestamps = context.get('description_timestamps', [])
        duration = context.get('duration_seconds')
        for i, ts in enumerate(description_timestamps):
            if i > 0 and ts['offset'] < description_timestamps[i - 1]['offset']:
                print(f"  [warn] Description timestamp {ts['offset']} is not ascending")
            if duration and ts['offset'] > duration:
                print(f"  [warn] Description timestamp {ts['offset']} exceeds duration {duration}")

    @classmethod
    def _assemble(cls, video, context, extracted, source_trace, evaluation):
        batch_time = Context.get().batch_time
        return {
            'extracted_at': batch_time.isoformat(),
            'video_id': video.video_id,
            'video_last_updated': video.last_updated.isoformat(),
            'prompt_version': cls.PROMPT_VERSION,
            'unique_length': context['unique_length'],
            'formats': extracted['formats'],
            'episode': extracted['episode'],
            'speakers': extracted['speakers'],
            'entities': extracted['entities'],
            'concepts': extracted['concepts'],
            'relationships': extracted['relationships'],
            'sources': extracted['sources'],
            'source_trace': source_trace,
            'evaluation': evaluation,
            'text': cls._format_text(extracted, context['description_timestamps']),
        }

    @classmethod
    def get_description_timestamps(cls, video):
        """Return [(offset_seconds, title), ...] parsed from video.description.
        Mechanical extraction — no LLM, no cached JSON involvement."""
        return [
            [ts['offset'], ts['description']]
            for ts in cls.extract_description_timestamps(video.description)
        ]
