#!/bin/env python
from langchain_community.document_loaders.youtube import YoutubeLoader
from langchain.docstore.document import Document
from pprint import pprint

def patched_load(self) -> list[Document]:
    pprint(self)
    transcript = self._get_transcript()
    processed = " ".join(
        piece.text.strip(" ") if hasattr(piece, "text") else piece["text"].strip(" ")
        for piece in transcript
    )
    return [Document(page_content=processed, metadata={"url": self.video_url})]

YoutubeLoader.load = patched_load  # Apply the patch

#video_id = "9ShkrkQIx0w"
video_id = "9yPy3DeMUyI"

url = f"https://www.youtube.com/watch?v={video_id}"

loader = YoutubeLoader.from_youtube_url(url)
docs = loader.load()
for doc in docs:
    print(doc.page_content)
