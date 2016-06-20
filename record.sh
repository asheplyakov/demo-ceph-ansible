#!/bin/sh
set -e
video_bitrate='6000k'
audio_bitrate='128k'
video_size='1920x1080'
pulse_source='2' # USB headset, the number is not stable across reboots
out="${1:-/tmp/record.mp4}"

exec ffmpeg \
	-f x11grab -video_size $video_size -framerate 25 -i :0.0 \
	-f pulse -i $pulse_source \
	-codec:v libx264 -b:v $video_bitrate \
	-codec:a libmp3lame -b:a $audio_bitrate \
	-y $out
