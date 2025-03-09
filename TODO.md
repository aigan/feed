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
