#!/bin/env python
from youtube import get_youtube_client
from pprint import pprint
from datetime import datetime, timezone
from config import ROOT
from pathlib import Path
import json
import argparse
import googleapiclient.errors

batch_time = datetime.now(timezone.utc)
output_dir = ROOT / "data/youtube/subscriptions/active"

parser = argparse.ArgumentParser(description="Unsubscribe from a YouTube channel.")
parser.add_argument("channel_id", help="The ID of the channel to remove")
args = parser.parse_args()

def unsubscribe(subscription_id):
    youtube = get_youtube_client()
    try:
        youtube.subscriptions().delete(id=subscription_id).execute()
        return True
    except googleapiclient.errors.HttpError as e:
        if e.resp.status == 404:
            print("Error: Subscription not found (404)")
        elif e.resp.status == 403:
            print("Error: Not allowed to unsubscribe (403)")
        else:
            print(f"Unexpected HTTP Error {e.resp.status}: {e.content}")
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
    return False

channel_id = args.channel_id
src_file = output_dir / f"{channel_id}.json"
data = json.loads(src_file.read_text())
subscription_id = data['subscription_id']


print(f"Unsubscribe {subscription_id}")
unsubscribe(subscription_id) 

# Todo: append status info to subscription record for inaccessible channels

#pprint(data)

