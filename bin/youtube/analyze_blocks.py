#!/bin/env python

import argparse
from youtube import Video
from analysis.description_filter import DescriptionFilter

parser = argparse.ArgumentParser()
parser.add_argument("video_id")
args = parser.parse_args()

video = Video.get(args.video_id)
blocks = DescriptionFilter.split_blocks(video.description)

print('\n§§§\n'.join(blocks))
