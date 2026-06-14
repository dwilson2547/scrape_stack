#!/bin/sh
set -e

# Render nginx config from template using environment variables.
# Falls back to sensible defaults matching the docker-compose service names.
export NGINX_RESOLVER="${NGINX_RESOLVER:-127.0.0.11}"
export API_HOST="${API_HOST:-cache-browser-api}"
export API_PORT="${API_PORT:-8040}"
export WEBCACHE_HOST="${WEBCACHE_HOST:-webcache}"
export WEBCACHE_PORT="${WEBCACHE_PORT:-8000}"
export IMGCACHE_HOST="${IMGCACHE_HOST:-imgcache}"
export IMGCACHE_PORT="${IMGCACHE_PORT:-8010}"
export FILECACHE_HOST="${FILECACHE_HOST:-filecache}"
export FILECACHE_PORT="${FILECACHE_PORT:-8030}"
export VIDCACHE_HOST="${VIDCACHE_HOST:-vidcache}"
export VIDCACHE_PORT="${VIDCACHE_PORT:-8020}"

envsubst '${NGINX_RESOLVER} ${API_HOST} ${API_PORT} ${WEBCACHE_HOST} ${WEBCACHE_PORT} ${IMGCACHE_HOST} ${IMGCACHE_PORT} ${FILECACHE_HOST} ${FILECACHE_PORT} ${VIDCACHE_HOST} ${VIDCACHE_PORT}' \
  < /etc/nginx/templates/nginx.conf.template \
  > /etc/nginx/conf.d/default.conf

exec nginx -g "daemon off;"
