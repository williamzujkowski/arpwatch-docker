#!/usr/bin/env python3
import re
import time
import logging
import os
import signal
import sys
from prometheus_client import start_http_server, Counter, Gauge

# Configuration
LOG_FILE = os.getenv('ARPWATCH_LOG_FILE', '/var/log/arpwatch.log')
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))
METRICS_ADDR = os.getenv('METRICS_ADDR', '0.0.0.0')

# Arpwatch event patterns and corresponding metrics
PATTERNS_AND_METRICS = {
    'new_station': {
        'pattern': re.compile(r'arpwatch: new station', re.IGNORECASE),
        'metric': Counter('arpwatch_new_station_total', 'Total new stations detected')
    },
    'flip_flop': {
        'pattern': re.compile(r'arpwatch: flip flop', re.IGNORECASE),
        'metric': Counter('arpwatch_flip_flop_total', 'Total flip flop events (potential ARP spoofing)')
    },
    'changed_ethernet': {
        'pattern': re.compile(r'arpwatch: changed ethernet address', re.IGNORECASE),
        'metric': Counter('arpwatch_changed_ethernet_total', 'Total ethernet address changes')
    },
    'reused_ethernet': {
        'pattern': re.compile(r'arpwatch: reused old ethernet address', re.IGNORECASE),
        'metric': Counter('arpwatch_reused_ethernet_total', 'Total reused ethernet addresses')
    },
    'bogon': {
        'pattern': re.compile(r'arpwatch: bogon', re.IGNORECASE),
        'metric': Counter('arpwatch_bogon_total', 'Total bogon events (invalid network activity)')
    },
    'ethernet_mismatch': {
        'pattern': re.compile(r'arpwatch: ethernet mismatch', re.IGNORECASE),
        'metric': Counter('arpwatch_ethernet_mismatch_total', 'Total ethernet mismatch events')
    },
    'ethernet_broadcast': {
        'pattern': re.compile(r'arpwatch: ethernet broadcast', re.IGNORECASE),
        'metric': Counter('arpwatch_ethernet_broadcast_total', 'Total ethernet broadcast events')
    },
    'ip_broadcast': {
        'pattern': re.compile(r'arpwatch: ip broadcast', re.IGNORECASE),
        'metric': Counter('arpwatch_ip_broadcast_total', 'Total IP broadcast events')
    },
    'new_activity': {
        'pattern': re.compile(r'arpwatch: new activity', re.IGNORECASE),
        'metric': Counter('arpwatch_new_activity_total', 'Total new activity events (first time in 6+ months)')
    },
    'suppressed_decnet': {
        'pattern': re.compile(r'arpwatch: suppressed.*flip flop', re.IGNORECASE),
        'metric': Counter('arpwatch_suppressed_decnet_total', 'Total suppressed DECnet flip flop events')
    }
}

# Additional metrics
last_activity = Gauge('arpwatch_last_activity_timestamp', 'Timestamp of last arpwatch log activity')
total_events = Counter('arpwatch_total_events', 'Total arpwatch events processed')

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('arpwatch_exporter')

# Global flag for graceful shutdown
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_flag
    logger.info(f"Received signal {signum}, initiating graceful shutdown")
    shutdown_flag = True


def follow(f):
    """Follow a file like tail -f, with error handling"""
    try:
        f.seek(0, 2)  # Go to end of file
        while not shutdown_flag:
            line = f.readline()
            if not line:
                time.sleep(0.1)
                continue
            yield line.strip()
    except Exception as e:
        logger.error(f"Error while following log file: {e}")
        raise


def wait_for_log_file(filepath, max_wait=60):
    """Wait for log file to exist, with timeout"""
    wait_time = 0
    while not os.path.exists(filepath) and wait_time < max_wait:
        logger.info(f"Waiting for log file {filepath} to exist...")
        time.sleep(2)
        wait_time += 2

    if not os.path.exists(filepath):
        raise FileNotFoundError(
            f"Log file {filepath} not found after {max_wait}s"
        )

    logger.info(f"Log file {filepath} found")


if __name__ == '__main__':
    # Set up signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    logger.info("Starting Arpwatch Prometheus exporter")
    logger.info(f"Metrics server: {METRICS_ADDR}:{METRICS_PORT}")
    logger.info(f"Log file: {LOG_FILE}")

    try:
        # Start metrics server
        start_http_server(METRICS_PORT, addr=METRICS_ADDR)
        logger.info("Started Prometheus exporter")

        # Wait for log file to exist
        wait_for_log_file(LOG_FILE)

        # Start log monitoring
        logger.info(f"Starting log monitoring on {LOG_FILE}")
        with open(LOG_FILE, 'r') as logfile:
            for line in follow(logfile):
                if shutdown_flag:
                    break

                # Update last activity timestamp
                last_activity.set_to_current_time()
                
                # Check each arpwatch event pattern
                event_found = False
                for event_type, config in PATTERNS_AND_METRICS.items():
                    if config['pattern'].search(line):
                        config['metric'].inc()
                        total_events.inc()
                        event_found = True
                        logger.debug(f"Detected {event_type}: {line}")
                        break  # Only count first match to avoid double-counting
                
                # Log unrecognized arpwatch lines for debugging
                if 'arpwatch:' in line and not event_found:
                    logger.debug(f"Unrecognized arpwatch event: {line}")

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except FileNotFoundError as e:
        logger.error(f"Log file error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        sys.exit(1)
    finally:
        logger.info("Arpwatch exporter shutdown complete")
