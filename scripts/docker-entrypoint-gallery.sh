#!/bin/sh
# Runs as root, then drops to aiartist.
#
# Railway allows one volume per service. When one is mounted at
# /app/persist, keep the SQLite DB (data/) and generated art (gallery/) on it
# so redeploys stop wiping likes, comments, collections and images. Without
# the mount this is a no-op and both stay in the container filesystem.
set -e

PERSIST=/app/persist
if [ -d "$PERSIST" ]; then
    for d in data gallery; do
        mkdir -p "$PERSIST/$d"
        if [ -d "/app/$d" ] && [ ! -L "/app/$d" ]; then
            # Seed files shipped in the image without overwriting saved state,
            # then move the image copy aside so the symlink can take its place.
            cp -Rn "/app/$d/." "$PERSIST/$d/" 2>/dev/null || true
            mv "/app/$d" "/app/.$d.image"
        fi
        [ -L "/app/$d" ] || ln -s "$PERSIST/$d" "/app/$d"
    done
    chown -R aiartist:aiartist "$PERSIST"
fi

mkdir -p /app/gallery /app/data
chown aiartist:aiartist /app/gallery /app/data 2>/dev/null || true
exec gosu aiartist "$@"
