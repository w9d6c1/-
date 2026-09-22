#!/bin/sh
# WAF wrapper: let entrypoint generate ModSecurity config, then replace default.conf

/docker-entrypoint.sh nginx -t 2>/dev/null || true

cp /tmp/waf-proxy.conf /etc/nginx/conf.d/default.conf
cat /tmp/crs-exclusions.conf >> /etc/nginx/modsecurity.d/modsecurity.conf

exec nginx -g 'daemon off;'
