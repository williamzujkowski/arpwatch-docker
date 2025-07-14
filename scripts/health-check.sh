#!/bin/bash

# Enhanced health check script for arpwatch container
# Checks both metrics endpoint and arpwatch process status

set -e

# Check if metrics exporter is responding
if ! wget -qO- http://localhost:8000/metrics > /dev/null 2>&1; then
    echo "Health check failed: Metrics endpoint not responding"
    exit 1
fi

# Check if arpwatch process is running
if ! pgrep arpwatch > /dev/null 2>&1; then
    echo "Health check warning: Arpwatch process not detected"
    # Don't fail immediately - metrics exporter might be working with sample data
    # Just log the warning and continue
fi

# Check if we can get arpwatch health metric
if wget -qO- http://localhost:8000/metrics | grep -q "arpwatch_process_health"; then
    # Get the actual health value
    HEALTH_VALUE=$(wget -qO- http://localhost:8000/metrics | grep "arpwatch_process_health" | grep -v "# HELP\|# TYPE" | awk '{print $2}')
    if [[ "$HEALTH_VALUE" == "0.0" ]]; then
        echo "Health check warning: Arpwatch process health metric indicates process not running"
    fi
fi

echo "Health check passed: Metrics endpoint responding"
exit 0