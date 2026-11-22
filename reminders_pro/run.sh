#!/usr/bin/with-contenv bashio
bashio::log.info "Starting Reminders Pro ..."
cd /app
exec python3 -u /app/main.py
