# Span Tech CRM — runs on any machine with Docker, no build step required.
FROM node:22-alpine

RUN apk add --no-cache tini

WORKDIR /app

# The application has no npm dependencies; package.json is copied for metadata
# and the run scripts only.
COPY package.json ./
COPY server ./server
COPY public ./public

RUN mkdir -p /app/data && addgroup -S app && adduser -S app -G app \
    && chown -R app:app /app
USER app

ENV NODE_ENV=production \
    PORT=8080 \
    HOST=0.0.0.0 \
    DB_PATH=/app/data/spantech.db

EXPOSE 8080
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=4s --start-period=10s --retries=3 \
  CMD wget -qO- http://127.0.0.1:8080/api/health >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["node", "--no-warnings", "server/index.js"]
