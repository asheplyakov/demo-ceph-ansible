#!/bin/sh
set -e

screen_size () {
	xrandr -q | sed -rne '
	/^[A-Za-z][a-zA-Z0-9]*\s+connected/,/^[A-Za-z][a-zA-Z0-9]*\s+disconnected/ {
		s/^\s*([0-9x]+)\s+[0-9.]+[*].*$/\1/p
        }
	'
}

# https://trac.ffmpeg.org/wiki/Encode/H.264
VIDEO_CRF=20
# https://trac.ffmpeg.org/wiki/Encode/MP3
AUDIO_QUALITY=6 # 100 -- 130 kb/s, good enough for a speach
video_size="`screen_size`"
pulse_source='2' # USB headset, the number is not stable across reboots
out="${1:-/tmp/record.mp4}"

exec ffmpeg \
	-f x11grab -video_size $video_size -framerate 25 -i :0.0 \
	-f pulse -i $pulse_source \
	-codec:v libx264 -crf $VIDEO_CRF \
	-codec:a libmp3lame -q:a ${AUDIO_QUALITY} \
	-y $out
