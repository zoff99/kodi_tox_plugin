#! /bin/bash

rm -fv plugin.video.koditox.zip
zip -0 -r plugin.video.koditox.zip plugin.video.koditox/ -x "*.DS_Store" "__pycache__/*" \
 'plugin.video.koditox/addon.py___large' \
 'plugin.video.koditox/resources/lib/koditox.c__large' \
 'plugin.video.koditox/resources/lib/.gitignore'

