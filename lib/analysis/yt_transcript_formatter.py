from context import Context
from pprint import pprint
from typing import List

# Should use ytapi_extractor and yt_transcript_formatter to create a clean transcript

class YTTranscriptFormatter:
    PROMP_VERSION = 1
    CHUNK_SIZE = 120
    STEP_SIZE = 90

    @classmethod
    def get(cls, video):
        transcript = video.transcript()

        #from analysis import YTAPIVideoExtractor
        #summary = YTAPIVideoExtractor.get(video)
        #print(summary['text']);

        chunks = []
        chunk_id = 0

        while True:
            chunk_text = cls.get_chunk(video, transcript, chunk_id)
            if chunk_text is None:
                break
            chunks.append(chunk_text)
            chunk_id +=1

        text = cls.merge_transcript_chunks(chunks)
        pprint(cls.extract_headers_with_timestamps(text))
        return text

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
        if chunk_file.exists():
            return chunk_file.read_text()
        return cls.run_chunk(video, transcript, chunk_id)

    @classmethod
    def run_chunk(cls, video, transcript, chunk_id):
        offset = chunk_id * cls.STEP_SIZE
        chunk = cls.extract_transcript_segment(transcript, offset)
        if chunk is None:
            return None

        first_line = chunk.partition('\n')[0]
        print(f"Processing chunk {chunk_id}: {first_line}")

        prompt = """
Process this transcript chunk. Improve readability. Remove stutters or filler words. Some words may
be wrong because they sound similar to the real ones. Use the context to figure out what was
actually said. Create complete sentences but dont change any words from the original. Group sentences in paragraphs.

Insert a chapter heading when a clear new topic or theme begins. Only insert a heading when the conversation clearly shifts — such as starting a new discussion, answering a new question, or moving to a new aspect of the subject. You can skip headings if the topic doesn't shift. Avoid repeating similar headings.
Format chapter headings using a line starting with `## ` followed by the heading text.

Each paragraph must start with the timestamp (an integer in seconds), then a colon and a space, then the text. Do not use markdown.
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
            Skip them and begin at the first *new* paragraph.
            If the previous paragraph was incomplete you may *recreate and complete* it here,
            using the *exact same timestamp*.

            Previous context:
            ## [Paragraph -2]
            {paragraphs[-2]}

            ## [Paragraph -1, probably incomplete]
            {paragraphs[-1]}
            """

        import textwrap
        instructions = textwrap.dedent(instructions)

        text = cls.ask_llm(
            prompt,
            {
#                "summary": summary['text'],
                "transcript_chunk": chunk,
                "extra_instructions": instructions,
            },
            model="gpt-4o",
            temperature=0.4,
        )

        chunk_dir = cls.get_transcript_chunk_dir(video.video_id)
        chunk_file = chunk_dir / f'{chunk_id:03}.txt'
        chunk_file.parent.mkdir(exist_ok=True)
        chunk_file.write_text(text)
        return text

    @classmethod
    def ask_llm(
            cls,
            prompt: str,
            params: dict = None,
            *,
            model: str = 'gpt-4o-mini',
            temperature: float = 0.7,
            ) -> str:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        prompt_template = ChatPromptTemplate.from_template(prompt)
        llm = ChatOpenAI(model=model, temperature=temperature)
        chain = prompt_template | llm | StrOutputParser()
        return chain.invoke(params)

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
    def preview_prompt(cls, prompt: str, params: dict) -> str:
        from langchain_core.prompts import ChatPromptTemplate
        template = ChatPromptTemplate.from_template(prompt)
        prompt_value = template.format_prompt(**(params or {}))
        return prompt_value.to_string()

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
    def extract_headers_with_timestamps(cls, transcript_text: str):
        """
        Extract headers with their timestamps from transcript text.
        Remove duplicates where the preceding heading is exactly the same.

        Args:
            transcript_text: The full transcript text with headers and timestamps

        Returns:
            List of tuples [(timestamp, heading_text)] without exact duplicates
        """
        import re

        # Find all headers and timestamps in the text
        headers = [(m.group(1), m.start()) for m in re.finditer(r'^## (.+?)$', transcript_text, re.MULTILINE)]
        timestamps = [(int(m.group(1)), m.start()) for m in re.finditer(r'^(\d+):\s', transcript_text, re.MULTILINE)]

        if not headers or not timestamps:
            return []

        # Sort both lists by position
        headers.sort(key=lambda x: x[1])
        timestamps.sort(key=lambda x: x[1])

        # Pair each header with its following timestamp
        header_timestamps = []
        ts_index = 0

        for header_text, header_pos in headers:
            # Find the next timestamp after this header, continuing from last position
            while ts_index < len(timestamps) and timestamps[ts_index][1] <= header_pos:
                ts_index += 1

            # If we found a timestamp after this header, pair them
            if ts_index < len(timestamps):
                header_timestamps.append((timestamps[ts_index][0], header_text))

        return header_timestamps
