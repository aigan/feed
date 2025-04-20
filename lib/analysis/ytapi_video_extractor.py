from context import Context
from pprint import pprint
from analysis import Processor

class YTAPIVideoExtractor(Processor):
    PROMPT_VERSION = 1

    @classmethod
    def get(cls, video):
        from youtube import Video
        import json

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
        from youtube import Video, Transcript
        from util import dump_json

        video_id = video.video_id
        result_file = Video.get_processed_dir(video_id) / "ytapi_extracted.json"

        description = Transcript.process_timestamps(video.description)

        prompt = """
VIDEO METADATA EXTRACTION

Given the following video title, description, and tags, extract structured information about speakers, timestamps and topics.

SPEAKERS: Identify all speakers mentioned, including:
   - Full name. Search for the full name in title, description and tags and use common knowledge if its a well known person.
   - Roles (host, guest, narrator, interviewee, etc)
   - Short description with any professional titles or affiliations or relationships between speakers
   - Format as `{{full name}}: {{roles}}, {{description}}\n`
   - For each list item under SPEAKERS, do not use markdown formatting symbols.

TIMESTAMPS: Extract all timestamps and their associated topics or segments
   - Existing timestamps in HH:MM:ss format has been ammended with the corresponding timestamp as offset in seconds from the start. For example `[ts 177] 2:57 Chapter title`. Extract all timestamps and chapter descriptions, using the `[ts {{offset}}]`.
   - Format as `{{offset}}: {{topic description}}\n`
   - For each list item under TIMESTAMPS, do not use markdown formatting symbols, but make sure that the offset is an integer and not in the `MM:ss` format.

TOPICS: Identify key subject matter and themes from the content:
   - Primary topics of discussion
   - Specific projects, products, or works mentioned, if any
   - Advanced technical terminology or specialized concepts, if any
   - Historical references or comparisons, if any

NOTES: Note any additional contextual information:
   - Format: Interview, monologue, reaction, documentary, podcast, etc
   - Series: The series this video is part of, or `none`
   - Episode: If a series, which episode or installment
   - Sources: Is it reaction, commentary, analysis, etc. Format example: `Commentary on {{source video names}}`, or report as `Original content`.


Video Title: {title}
Video Description:
{description}
Video Tags: {tags}
        """

        text_result = cls.ask_llm(
            prompt,
            {
            "title": video.title,
            "description": description,
            "tags": ", ".join(video.tags),
            }
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
