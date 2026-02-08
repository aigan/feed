
from pprint import pprint

from analysis import Processor
from context import Context


class YTAPIVideoExtractor(Processor):
    PROMPT_VERSION = 1

    @classmethod
    def get(cls, video):
        import json

        from youtube import Video

        video_id = video.video_id
        result_file = Video.get_processed_dir(video_id) / "ytapi_extracted.json"
        if result_file.exists():
            result = json.loads(result_file.read_text())
            if (result['prompt_version'] == cls.PROMPT_VERSION and
                result['video_last_updated'] == video.last_updated.isoformat()):
                return result
        return cls.run(video)

    @classmethod
    def run(cls, video):
        from util import dump_json
        from youtube import Transcript, Video

        video_id = video.video_id
        result_file = Video.get_processed_dir(video_id) / "ytapi_extracted.json"

        description = Transcript.process_timestamps(video.description)

        prompt = """
VIDEO METADATA EXTRACTION

Given the following video metadata, extract structured information in the sections below.

For **every output line**, append exactly one CONFIDENCE TAG:
  [!]   = confident (exact match in input)
  [?]   = plausible (slightly reworded from input)
  [??]  = speculative (inferred from context)
  [???] = no data available

FORMAT:
Select one or more formats from the following list. Output as `<format label> <confidence tag>` with one line per entry.
 - interview: one‑on‑one Q&A with host and guest
 - discussion: multi‑voice roundtable or panel
 - monologue: single speaker addressing the audience
 - presentation: structured talk or keynote with visuals/slides
 - documentary: edited, fact‑driven narrative with multiple sources
 - essay: scripted, argument‑driven analysis
 - review: evaluative critique of a product or work
 - reaction: creator’s real‑time or first‑view response to external media (faces, brief remarks)
 - commentary: creator adds substantive discussion or analysis (pauses, explains, breaks down)
 - embed: external media shown largely unaltered and central to the video
 - letsplay: gameplay footage with live commentary
 - news: report on current events or announcements
 - tutorial: step‑by‑step instructional content
 - vlog: personal or behind‑the‑scenes video log
 - compilation: curated collection of clips or highlights
 - livestream: real‑time broadcast, often interactive
 - skit: short scripted fictional or comedic piece
 - other: format that doesn’t fit or mixes types equally


EPISODE:
If a series, extract both the series title and episode number or name, if present. Otherwise, write none. Output as `<series>: <episode> <confidence tag>`.

SPEAKERS:
Identify all speakers mentioned, including:
 - Full name. Use metadata and common knowledge (e.g., resolve known handles to names).
 - Roles: host, guest, narrator, interviewee, etc.
 - Short description: Include affiliations, professional titles, or notable relationships.
 - Format as `<full name>: <roles>, <description> <confidence tag>` with one line per entry; no markdown.
 - Each speaker must also appear under ENTITIES using the same full name.

TIMESTAMPS:
Extract all timestamps and their associated topics or segments
 - Existing timestamps in HH:MM:ss format have been amended with the corresponding timestamp as offset in seconds from the start. For example `[ts 177] 2:57 Chapter title`. Extract all timestamps and chapter descriptions, using the `[ts <offset>]`.
 - Format as `<offset>: <topic description>`
 - For each list item under TIMESTAMPS, do not use markdown formatting symbols, but make sure that the offset is an integer and not in the `MM:ss` format. The first timestamp should be `0: <topic description>`.

ENTITIES:
List all named entities; real, fictional, or speculative. If mentioned in the input, include online handles, channel names, URLs, or other aliases in a comma-separated list inserted in the <aliases> position. Format each row with `<canonical term> (<category>) <aliases> <confidence tag>`. Use these categories:
- person: A named individual or sentient agent, including humans, characters, AI, animals, spirits, avatars, or mythical beings.
- organization: Any named group, institution, company, movement, team, or faction.
- product: A named item such as a game, film, book, food, service, device, or software.
- workseries: A recurring or branded sequence of creative works or narratives, such as franchises, universes, or serialized shows.
- technology: Any named method, system, tool, engine, programming language, library, or platform.
- location: Any named place, including countries, cities, regions, virtual spaces, planets, or in-world environments.
- date: Any specific point or span in time, including years, eras, relative phrases, or projected timelines.
- event: Any occurrence or happening, such as launches, battles, releases, protests, ceremonies, or historical/cultural moments.
If a named item does not clearly match any of the above categories, do not include it under ENTITIES — use the CONCEPTS section instead.

CONCEPTS:
List key ideas using keyword and description. The keyword should be a concise term, followed by a brief description explaining its context in this video. Do not include disclaimers, copyright notices, standard calls to action, or boilerplate metadata unless clearly framed as part of the video’s actual topic. Format each row with `<canonical term>: <description> <confidence tag>`.

RELATIONSHIPS:
List important connections between entities or concepts mentioned above, showing how they relate to each other. Format each row with two or more entities with `<entity 1> + <entity 2> + <entity 3>: <relationship description> <confidence tag>`

SOURCES:
List each distinct external item the video cites, reacts to, summarizes, or is clearly based on  —  such as videos, events, books, news stories, posts, or products. Use only details found in the input. If a source is unnamed, supply a concise descriptive label. Where available, include identifying clues (speaker, quoted title, date, venue, or platform) to aid later retrieval, and merge duplicates that refer to the same material. If a source includes a URL, place it at the end of the line, space-separated. If no URL is given, output an empty string instead. Remember to also add confidence tags if the source is uncertain. Output `<source description> (<clues>) <URL>  <confidence tag>`, with one source per row.

VALUE:
Evaluate the video across the following criteria. Output `<criteria label> <score> <confidence tag> with one row per criteria (insight, novelty, quality, delivery).
Use [!] only when there is enough description about the content to confidently assign a score
Use [?] if the tone or phrasing strongly hints at the likely score, but it's not explicit.
Use [??] if you're making a weak guess or the part of the description about the content is less than 100 words.
Use [???] if there is no solid basis to score — especially for insight, quality, or delivery.

Do not assign a score of 4 or 5 unless the metadata clearly indicates strong structure, novelty, or credibility. When in doubt, favor leaving the score blank or assigning a low score.

* Insight
  5: Reveals underlying systems, root causes, or transformative mechanisms.
  4: Offers structured reasoning or connects ideas meaningfully.
  3: Raises thoughtful points but lacks depth or system framing.
  2: Mostly descriptive with limited analysis or framing.
  1: Lists facts or opinions with no explanation or structure.

* Novelty
  5: Presents rare angles, underreported stories, or original framings.
  4: Covers newer or less saturated developments.
  3: Somewhat familiar, but includes minor fresh context or synthesis.
  2: Repetitive or derivative of common narratives.
  1: Predictable, recycled, or no new information at all.

* Quality
  5: Thoughtful, evidence-based, balanced, and intellectually honest.
  4: Clear logic with minor bias or simplification.
  3: Mixed reasoning; some overreach or omission.
  2: Uses emotional hooks, partisanship, or flawed logic.
  1: Manipulative, dishonest, or structurally incoherent.

* Delivery
  5: High insight density and excellent production craft—engaging voice, smart editing, visual support, music, or atmosphere enhance clarity and impact.
  4: Mostly well-paced or well-crafted; some standout elements in format or presentation.
  3: Competent but uneven—some distracting flaws or missed opportunities in format.
  2: Poor pacing or low production effort; distracting, unclear, or aesthetically flat.
  1: Visually or aurally unpleasant, incoherent, or unserious in tone vs. topic.


Video Title: {title}
Upload date: {date}
Length: {length}
Description:
{description}
Tags: {tags}
        """

        text_result = cls.ask_llm(
            prompt,
            {
                "title": video.title,
                "description": description,
                "date": video.published_at,
                "length": video.duration_formatted,
                "tags": ", ".join(video.tags) if video.tags else "No tags",
            },
            model = 'gpt-4.1',
        )

        batch_time = Context.get().batch_time
        result = {
            "extracted_at": batch_time.isoformat(),
            "video_id": video_id,
            "video_last_updated": video.last_updated.isoformat(),
            "prompt_version": cls.PROMPT_VERSION,
            "text": text_result,
        }

        #pprint(result)
        dump_json(result_file, result)

        return result

    @classmethod
    def get_chapters(cls, video):
        import re
        summary = cls.get(video)['text']

        timestamp_match = re.search(r'TIMESTAMPS:(.*?)(\n\s*\n|\Z)', summary, re.DOTALL)
        if not timestamp_match: return []

        chapter_re = r'(?P<seconds>\d+): (?P<description>.*?)(?=\n\d+:|$)'
        chapter_matches = re.finditer(chapter_re, timestamp_match.group(1), re.DOTALL)

        return [[int(m['seconds']), m['description'].strip()] for m in chapter_matches]
