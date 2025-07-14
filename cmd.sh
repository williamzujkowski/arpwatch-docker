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

# Function to inject sample data for demonstration
inject_sample_data() {
    local current_date
    current_date=$(date '+%b %d %H:%M:%S')
    
    echo "Injecting sample arpwatch data for demonstration..."
    
    # Sample entries with realistic MAC addresses and timing
    cat >> "$LOG_FILE" << EOF
${current_date} arpwatch-monitor arpwatch: new station 192.168.1.101 d4:81:d7:23:a5:67 eth0
${current_date} arpwatch-monitor arpwatch: new station 192.168.1.102 6c:40:08:9a:bc:de eth0
${current_date} arpwatch-monitor arpwatch: new station 192.168.1.103 00:1e:c9:45:67:89 (printer-lobby.local) eth0
${current_date} arpwatch-monitor arpwatch: new station 192.168.1.104 00:1b:21:12:34:56 eth0
${current_date} arpwatch-monitor arpwatch: new station 10.0.0.50 ac:bc:32:78:9a:bc eth0
EOF
    
    echo "Sample data injected: 5 new station events added to ${LOG_FILE}"
}

# Inject sample data for demonstration (configurable)
if [[ "${ARPWATCH_DEMO_DATA:-true}" == "true" ]]; then
    inject_sample_data
else
    echo "Sample data injection disabled (ARPWATCH_DEMO_DATA=false)"
fi

# Brief pause to let metrics exporter process sample data
if [[ "${ARPWATCH_DEMO_DATA:-true}" == "true" ]]; then
    echo "Waiting 2 seconds for metrics processing..."
    sleep 2
fi

# Build and exec arpwatch
CMD_ARGS=(-u arpwatch -a -p)
[[ -n "${ARPWATCH_INTERFACE:-}" ]] && CMD_ARGS+=(-i "$ARPWATCH_INTERFACE")
[[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]] && CMD_ARGS+=(-m "$ARPWATCH_NOTIFICATION_EMAIL_TO")
exec /usr/local/sbin/arpwatch "${CMD_ARGS[@]}"