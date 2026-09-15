# Span Tech CRM — runs on any machine with Docker, no build step required.
FROM node:22-alpine

# tini reaps zombies and forwards signals; su-exec drops privileges in the
# entrypoint after it has fixed the bind-mounted data directory's ownership.
RUN apk add --no-cache tini su-exec

WORKDIR /app

# The application has no npm dependencies; package.json is copied for metadata
# and the run scripts only.
COPY package.json ./
COPY server ./server
COPY public ./public
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/docker-entrypoint.sh \
    && addgroup -S app && adduser -S app -G app \
    && mkdir -p /app/data \
    && chown -R app:app /app

# Starts as root so the entrypoint can chown the mounted volume, then runs the
# server as the unprivileged "app" user.
ENV NODE_ENV=production \
    PORT=8080 \
    HOST=0.0.0.0 \
    DB_PATH=/app/data/spantech.db

EXPOSE 8080
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/api/health >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/sbin/tini", "--", "/usr/local/bin/docker-entrypoint.sh"]
CMD ["node", "--no-warnings", "server/index.js"]
