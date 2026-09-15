#!/bin/sh
set -e

# The data directory is usually a bind mount from the host (./data), so it
# arrives owned by whoever cloned the repository — not by the container's
# unprivileged "app" user. Fix the ownership while we are still root, then
# drop privileges before starting the server.
if [ "$(id -u)" = "0" ]; then
  mkdir -p /app/data
  chown -R app:app /app/data
  exec su-exec app "$@"
fi

exec "$@"
