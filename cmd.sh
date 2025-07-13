#!/usr/bin/env bash
set -euo pipefail

LOG_FILE='/var/log/arpwatch.log'

# Ensure log directory and file exist
mkdir -p "$(dirname "$LOG_FILE")"
touch "$LOG_FILE"
chown arpwatch:arpwatch "$LOG_FILE"

# Validate email configuration (optional)
if [[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]]; then
    : "${ARPWATCH_NOTIFICATION_EMAIL_FROM:?Missing ARPWATCH_NOTIFICATION_EMAIL_FROM when EMAIL_TO is set}"
    : "${ARPWATCH_NOTIFICATION_EMAIL_SERVER:?Missing ARPWATCH_NOTIFICATION_EMAIL_SERVER when EMAIL_TO is set}"
    echo "Email notifications enabled for: ${ARPWATCH_NOTIFICATION_EMAIL_TO}"
else
    echo "Email notifications disabled - no ARPWATCH_NOTIFICATION_EMAIL_TO configured"
fi

# Start rsyslog in foreground
rsyslogd -f /rsyslog.conf

# Launch the metrics exporter
python3 /exporter/metrics_exporter.py &
echo "Started Prometheus exporter (pid $!)"

# Build and exec arpwatch
CMD_ARGS=(-u arpwatch -a -p)
[[ -n "${ARPWATCH_INTERFACE:-}" ]] && CMD_ARGS+=(-i "$ARPWATCH_INTERFACE")
[[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]] && CMD_ARGS+=(-m "$ARPWATCH_NOTIFICATION_EMAIL_TO")
exec /usr/local/sbin/arpwatch "${CMD_ARGS[@]}"