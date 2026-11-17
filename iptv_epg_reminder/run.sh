#!/usr/bin/with-contenv bashio
bashio::log.info "Starting IPTV EPG Reminders ..."
cd /app
exec python3 -u /app/main.py
