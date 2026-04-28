I would also like to know if a video was unliked. Not sure how to do that. Perhaps if the videos are returned in the same order, I could see if a video is missing in the result. 


... for getting more data about video, if availible:

youtube_analytics = build('youtubeAnalytics', 'v2', credentials=creds)
response = youtube_analytics.reports().query(
            ids="channel==MINE",  # Use "channel==MINE" to get data for your channel
            startDate=start_date,
            endDate=end_date,
            metrics=metrics,
            dimensions=dimensions,
            filters=f"video=={video_id}"
        ).execute()


## LLM model / config cleanup

- Empty extraction parser failure on gpt-5-mini and gpt-5.4-mini. On 1/8 and 2/8 videos respectively, the extractor emitted something `_parse_sections` couldn't read — results had empty `formats`/`speakers`/`entities`/`concepts` lists but a populated `evaluation.gaps` list. Nano variants produced structured sections on all 8 videos. Likely the bigger models occasionally wrap output in markdown fences or shift the `=== SECTION ===` delimiters. Fix either by tightening the prompt (add "do not wrap in markdown fences") or by making `_parse_sections` tolerant of code fences and loose delimiters.

