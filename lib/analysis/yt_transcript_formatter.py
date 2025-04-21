from context import Context
from pprint import pprint
from typing import List
from analysis import Processor

class YTTranscriptFormatter(Processor):
    PROMP_VERSION = 1
    CHUNK_SIZE = 400 # Up to 42 tokens per row
    STEP_SIZE = 370

    @classmethod
    def get(cls, video):
        from youtube import Video
        transcript_file = Video.get_processed_dir(video.video_id) / "transcript.txt"
        if transcript_file.exists(): return transcript_file.read_text()

        transcript = video.transcript()
        chunks = []
        chunk_id = 0

        while True:
            chunk_text = cls.get_chunk(video, transcript, chunk_id)
            if chunk_text is None:
                break
            chunks.append(chunk_text)
            chunk_id +=1

        transcript_text = cls.merge_transcript_chunks(chunks)
        headings_text = cls.get_cleanup_headings(video, transcript_text)
        result_text = cls.insert_headings_in_transcript(transcript_text, headings_text)

        transcript_file.write_text(result_text)
        return result_text

    @classmethod
    def extract_transcript_segment(cls, transcript, offset):
        result = ""
        end_index = min(offset + cls.CHUNK_SIZE, len(transcript['segments']))
        if offset >= end_index:
            return None
        for i in range(offset, end_index):
            segment = transcript['segments'][i]
            start = int(round(segment['start'],0))
            result += f"{start}: {segment['text']}\n"
        return result

    @classmethod
    def is_last_chunk(cls, transcript, chunk_id):
        next_chunk_offset = (chunk_id + 1) * cls.CHUNK_SIZE
        return next_chunk_offset >= len(transcript['segments'])
    
    @classmethod
    def get_chunk(cls, video, transcript, chunk_id):
        chunk_file = cls.get_transcript_chunk_dir(video.video_id) / f'{chunk_id:03}.txt'
        if chunk_file.exists(): return chunk_file.read_text()
        return cls.run_chunk(video, transcript, chunk_id)

    @classmethod
    def run_chunk(cls, video, transcript, chunk_id):
        import re
        offset = chunk_id * cls.STEP_SIZE
        chunk = cls.extract_transcript_segment(transcript, offset)
        if chunk is None: return None

        first_line = chunk.partition('\n')[0]
        print(f"Processing chunk {chunk_id}: {first_line}")

        prompt = """
Process this transcript chunk. Improve readability. Remove stutters or filler words. Some words may
be wrong because they sound similar to the real ones. Use the context to figure out what was
actually said. Create complete sentences but dont change any words from the original. Group sentences in paragraphs.

Insert a chapter heading when a clear new topic or theme begins. Only insert a heading when the conversation clearly shifts — such as starting a new discussion, answering a new question, or moving to a new aspect of the subject. You can skip headings if the topic doesn't shift. Avoid repeating similar headings. There should be a new hading at least every 2000 words or 600 seconds. Find the best spot for the headings. Include the word AD for sponsor segments, promotions and so on.
Format chapter headings using a line starting with `## ` followed by the heading text.

Each paragraph must start with the timestamp (an integer in seconds), then a colon and a space, then the text. Do not use markdown or any extra commentary or tags.
Example:  
123: Welcome to this new video.
        
{extra_instructions}

Transcript chunk:
{transcript_chunk}
        """

#        from analysis import YTAPIVideoExtractor
#        summary = YTAPIVideoExtractor.get(video)

        instructions = ""
        is_last = cls.is_last_chunk(transcript, chunk_id)
        if chunk_id == 0:
            if is_last:
                instructions = "This is the *whole* of the transcript"
            else:
                instructions = """
                This is the *beginning* of the transcript.
                Start new paragraphs and chapters naturally.
                Don't assume prior context.
                The end is probably incomplete.
                """
        else:
            previous_text = cls.get_chunk(video, transcript, chunk_id - 1)
            paragraphs = cls.get_last_paragraphs(previous_text)
            chunk_order = (
                "This is the *end* of the transcript." if is_last else "This is a middle chunk."
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

            match = re.match(r"^(\d+):", paragraphs[-1])
            start_ts = int(match.group(1))
            #print(f"Start at {start_ts}")
            chunk_lines = chunk.splitlines()
            for i, line in enumerate(chunk_lines):
                match = re.match(r"^(\d+):", line)
                if match and int(match.group(1)) >= start_ts:
                    chunk_lines.insert(i, "[START HERE]")
                    break
            chunk = "\n".join(chunk_lines)
            #print(chunk)
            #exit()

        import textwrap
        instructions = textwrap.dedent(instructions)

#        print(cls.preview_prompt(
#            prompt,
#            {
#                "transcript_chunk": chunk,
#                "extra_instructions": instructions,
#            },
#        ))
#        exit()

        text = cls.ask_llm(
            prompt,
            {
                "transcript_chunk": chunk,
                "extra_instructions": instructions,
            },
            model="gpt-4.1-mini",
            temperature=0.8,
        )

        chunk_dir = cls.get_transcript_chunk_dir(video.video_id)
        chunk_file = chunk_dir / f'{chunk_id:03}.txt'
        chunk_file.parent.mkdir(parents=True, exist_ok=True)
        chunk_file.write_text(text)
        return text

    @classmethod
    def get_transcript_chunk_dir(cls, video_id):
        from youtube import Video
        return Video.get_processed_dir(video_id) / "transcript_chunks"

    @classmethod
    def get_last_paragraphs(cls, text: str, count: int = 2) -> List[str]:
        import re
        #print(f"Get last paragraphs from:\n{text}\n");

        # filter lines that begin with digits, a colon, and a space
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

        Args:
            chunks: List of transcript chunks in order (oldest to newest)

        Returns:
            Merged transcript as a string
        """
        if not chunks:
            return ""
        if len(chunks) == 1:
            return chunks[0]

        result = []
        previous_chunk = chunks[0]

        for current_chunk in chunks[1:]:
            current_first_timestamp = cls.extract_first_timestamp(current_chunk)

            if current_first_timestamp is not None:
                # Keep only parts of previous chunk before the current chunk starts
                previous_lines = previous_chunk.strip().split('\n')
                cut_index = next((i for i, line in enumerate(previous_lines)
                                if cls.extract_timestamp_from_line(line) is not None and
                                cls.extract_timestamp_from_line(line) >= current_first_timestamp),
                                len(previous_lines))

                result.append('\n'.join(previous_lines[:cut_index]))
            else:
                # No timestamp found, keep entire previous chunk
                result.append(previous_chunk)

            previous_chunk = current_chunk

        # Add the final chunk
        result.append(previous_chunk)

        return '\n'.join(filter(None, result))

    @classmethod
    def extract_headings_with_timestamps(cls, transcript_text: str):
        """
        Extract headings with their timestamps from transcript text.
        Remove duplicates where the preceding heading is exactly the same.

        Args:
            transcript_text: The full transcript text with headings and timestamps

        Returns:
            List of tuples [(timestamp, heading_text)] without exact duplicates
        """
        import re

        # Find all headings and timestamps in the text
        headings = [(m.group(1), m.start()) for m in re.finditer(r'^## (.+?)$', transcript_text, re.MULTILINE)]
        timestamps = [(int(m.group(1)), m.start()) for m in re.finditer(r'^(\d+):\s', transcript_text, re.MULTILINE)]

        if not headings or not timestamps: return []

        # Sort both lists by position
        headings.sort(key=lambda x: x[1])
        timestamps.sort(key=lambda x: x[1])

        # Pair each header with its following timestamp
        header_timestamps = []
        ts_index = 0

        for header_text, header_pos in headings:
            # Find the next timestamp after this header, continuing from last position
            while ts_index < len(timestamps) and timestamps[ts_index][1] <= header_pos:
                ts_index += 1

            # If we found a timestamp after this header, pair them
            if ts_index < len(timestamps):
                header_timestamps.append((timestamps[ts_index][0], header_text))

        return header_timestamps

    @classmethod
    def merge_headings(cls, video, transcript_text: str):
        from analysis import YTAPIVideoExtractor
        manual = YTAPIVideoExtractor.get_chapters(video)

        auto = cls.extract_headings_with_timestamps(transcript_text)

        labeled_manual = [[offset, 'manual', text] for offset, text in manual]
        labeled_auto   = [[offset, 'auto',   text] for offset, text in auto]

        labeled = labeled_manual + labeled_auto
        labeled.sort(key=lambda x: x[0])

        merged = []
        for i, (offset, source, text) in enumerate(labeled):
            delta_prev = offset - labeled[i-1][0] if i > 0 else None
            delta_next = labeled[i+1][0] - offset if i < len(labeled) - 1 else None
            merged.append([offset, source, delta_prev, delta_next, text])

        threshold = 30
        result = []
        i = -1
        last = len(merged) - 1

        while i < last:
            i += 1
            #print(f"Processing row {i}")
            offset, source, delta_prev, delta_next, text = merged[i]

            if source == "auto":
                if (i > 0):
                    p_offset, p_source, *_, p_text = merged[i-1]
                    if (p_source == "manual" and delta_prev <= threshold):
                        result.pop()
                        result.append([offset, "manual", p_text])
                        continue

                if (i < last):
                    n_offset, n_source, *_, n_text = merged[i+1]
                    if (n_source == "manual" and delta_next <= threshold):
                        result.append([offset, "manual", n_text])
                        i += 1
                        continue

            result.append([offset, source, text])

        return result

    @classmethod
    def get_cleanup_headings(cls, video, transcript_text: str):
        from youtube import Video
        headings_file = Video.get_processed_dir(video.video_id) / "headings.txt"
        if headings_file.exists(): return headings_file.read_text()
        return cls.run_cleanup_headings(video, transcript_text)

    @classmethod
    def run_cleanup_headings(cls, video, transcript_text: str):
        from youtube import Video
        headings_file = Video.get_processed_dir(video.video_id) / "headings.txt"
        #pprint(cls.merge_headings(video, transcript_text))

        headings_text = "";
        for offset, source, text in cls.merge_headings(video, transcript_text):
            headings_text += f"{offset} {source}: {text}\n"

        print(headings_text)
        headings_file.write_text(headings_text)

        prompt =  """
Process the following time‑sorted lines, each in the form "<seconds> <source>: <title>", into a clean Table of Contents.

`manual` lines are main chapters (##) and last until the next manual line or video end.

Discard any `auto` lines less than about 120 seconds after previous heading unless either title clearly signals a distinct shorter segment such as ads, promos, or housekeeping.

Output the final list in the input seconds order, with no extra commentary. Use the format:
<seconds> ## Title
<seconds> ### Subtopic

HEADINGS:
{headings}
        """

        text = cls.ask_llm(
            prompt,
            {
                'headings': headings_text,
            },
            model = 'gpt-4.1',
            temperature = 1,
        )
        headings_file.write_text(text)
        print(text)
        return text

    @classmethod
    def insert_headings_in_transcript(cls, transcript_text: str, headings_text: str):
        import re
        timestamps = [(int(m.group(1)), 1, m.group(0)) for m in re.finditer(r'^(\d+): (.+)$', transcript_text, re.MULTILINE)]
        headings = [(int(m.group(1)), 0, m.group(2)) for m in re.finditer(r'^(\d+) (#.+)$', headings_text, re.MULTILINE)]

        merged = timestamps + headings
        merged.sort(key=lambda x: (x[0], x[1]))

        result = ""
        for key, prio, line in merged:
            result += line + "\n\n"

        return result
