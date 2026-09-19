#!/bin/sh
# Top the data volume up from the image's seed copy. `-n` never overwrites, so a
# redeploy keeps HR-authored jobs, uploads and the audit chain, while demo CVs
# added in a newer image still appear on an existing volume.
set -e

mkdir -p /app/data /app/data/jobs /app/data/uploads
if [ -d /app/data-seed ]; then
    cp -rn /app/data-seed/. /app/data/
fi

exec "$@"
