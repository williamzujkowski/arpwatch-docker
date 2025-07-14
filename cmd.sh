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

# Start rsyslog - arpwatch may need it for logging even without email
echo "Starting rsyslog for arpwatch logging..."
rsyslogd -f /rsyslog.conf || echo "Failed to start rsyslog, continuing anyway"

# Launch the metrics exporter
python3 /exporter/metrics_exporter.py &
EXPORTER_PID=$!
echo "Started Prometheus exporter (pid $EXPORTER_PID)"

# Function to inject sample data for demonstration
inject_sample_data() {
    local current_date
    current_date=$(date '+%b %d %H:%M:%S')
    
    echo "Injecting comprehensive arpwatch sample data for demonstration..."
    
    # Brief pause to ensure metrics exporter is ready
    sleep 1
    
    # Comprehensive sample data covering all arpwatch event types
    cat >> "$LOG_FILE" << EOF
${current_date} arpwatch-monitor arpwatch: new station 192.168.1.101 d4:81:d7:23:a5:67 docker0
${current_date} arpwatch-monitor arpwatch: new station 192.168.1.102 6c:40:08:9a:bc:de docker0
${current_date} arpwatch-monitor arpwatch: flip flop 192.168.1.105 00:aa:bb:cc:dd:ee (00:11:22:33:44:55) docker0
${current_date} arpwatch-monitor arpwatch: changed ethernet address 192.168.1.200 00:50:56:a1:b2:c3 (00:0c:29:87:65:43) docker0
${current_date} arpwatch-monitor arpwatch: reused old ethernet address 192.168.1.150 00:1b:21:3c:4d:5e docker0
${current_date} arpwatch-monitor arpwatch: bogon 8.8.8.8 00:1e:52:81:24:eb docker0
${current_date} arpwatch-monitor arpwatch: ethernet mismatch 192.168.1.180 00:25:90:12:34:56 (00:25:90:ab:cd:ef) docker0
${current_date} arpwatch-monitor arpwatch: new activity 192.168.1.125 00:0c:29:87:65:43 docker0
${current_date} arpwatch-monitor arpwatch: ethernet broadcast 192.168.1.255 ff:ff:ff:ff:ff:ff docker0
${current_date} arpwatch-monitor arpwatch: ip broadcast 192.168.1.255 00:1a:2b:3c:4d:5e docker0
EOF
    
    echo "Sample data injected: 10 diverse arpwatch events added to ${LOG_FILE}"
    echo "Event types: new station, flip flop, changed ethernet, reused ethernet, bogon, ethernet mismatch, new activity, ethernet broadcast, ip broadcast"
}

# Inject sample data for demonstration (configurable)
if [[ "${ARPWATCH_DEMO_DATA:-true}" == "true" ]]; then
    inject_sample_data
else
    echo "Sample data injection disabled (ARPWATCH_DEMO_DATA=false)"
fi

# Brief pause to let metrics exporter process sample data
if [[ "${ARPWATCH_DEMO_DATA:-true}" == "true" ]]; then
    echo "Waiting 3 seconds for metrics processing..."
    sleep 3
fi

# Build and exec arpwatch
# Run arpwatch in foreground and background it with &
CMD_ARGS=()

# Detect and set appropriate interface
# Prefer wired interfaces over wireless for arpwatch reliability
if [[ -n "${ARPWATCH_INTERFACE:-}" ]]; then
    INTERFACE="$ARPWATCH_INTERFACE"
elif [[ -e "/sys/class/net/eth0" ]]; then
    INTERFACE="eth0"
elif [[ -e "/sys/class/net/docker0" ]]; then
    INTERFACE="docker0"  # Docker bridge often works well
elif [[ -e "/sys/class/net/wlp166s0" ]]; then
    INTERFACE="wlp166s0"  # Wireless as fallback
else
    # Find first non-loopback, non-virtual interface
    INTERFACE=$(ls /sys/class/net/ | grep -E '^(eth|ens|enp)' | head -1)
    if [[ -z "$INTERFACE" ]]; then
        # Fallback to any non-loopback interface
        INTERFACE=$(ls /sys/class/net/ | grep -v lo | head -1)
    fi
fi

if [[ -z "$INTERFACE" ]]; then
    echo "No suitable network interface found. Available interfaces:"
    ls /sys/class/net/ || echo "Cannot list network interfaces"
    INTERFACE="lo"  # Fallback to loopback
fi

# Add data file (arpwatch database)
CMD_ARGS+=(-f /var/lib/arpwatch/arp.dat)

CMD_ARGS+=(-i "$INTERFACE")
[[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]] && CMD_ARGS+=(-m "$ARPWATCH_NOTIFICATION_EMAIL_TO")

echo "Starting arpwatch with interface: $INTERFACE"
echo "Available interfaces: $(ls /sys/class/net/ 2>/dev/null | tr '\n' ' ')"
echo "Command: /usr/local/sbin/arpwatch ${CMD_ARGS[*]}"

# Check if interface exists and is accessible
if [[ ! -e "/sys/class/net/$INTERFACE" ]]; then
    echo "Warning: Interface $INTERFACE does not exist"
fi

# Try to start arpwatch with better error reporting
echo "Running as user: $(whoami)"
echo "Checking arpwatch capabilities: $(getcap /usr/local/sbin/arpwatch 2>/dev/null || echo 'No capabilities found')"

# Start arpwatch in background
if /usr/local/sbin/arpwatch "${CMD_ARGS[@]}" &
then
    ARPWATCH_PID=$!
    echo "Arpwatch started successfully in background (PID: $ARPWATCH_PID)"
    
    # Give arpwatch more time to start and initialize
    sleep 5
    
    # Check if arpwatch is still running
    if kill -0 "$ARPWATCH_PID" 2>/dev/null; then
        echo "Arpwatch process confirmed running and healthy"
        echo "Arpwatch is monitoring interface: $INTERFACE"
    else
        echo "Warning: Arpwatch process stopped after starting"
    fi
    
    echo "Container will now keep running to maintain metrics exporter and arpwatch"
    # Keep container alive so both metrics exporter and arpwatch continue working
    tail -f /dev/null
else
    EXIT_CODE=$?
    echo "Arpwatch failed to start (exit code: $EXIT_CODE)"
    echo "Attempting to run arpwatch with different parameters..."
    
    # Try basic command to diagnose
    CMD_ARGS_TEST=(-f /var/lib/arpwatch/arp.dat -i "$INTERFACE")
    
    echo "Trying command: /usr/local/sbin/arpwatch ${CMD_ARGS_TEST[*]}"
    if timeout 5 /usr/local/sbin/arpwatch "${CMD_ARGS_TEST[@]}" 2>&1 | head -10; then
        echo "Arpwatch can run but may need different configuration"
    else
        echo "Arpwatch fails with basic parameters too"
    fi
    
    echo ""
    echo "Metrics exporter will continue running for demonstration purposes"
    # Keep container alive so metrics exporter continues working
    tail -f /dev/null
fi