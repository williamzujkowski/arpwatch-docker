#!/usr/bin/env python3
import re
import time
import logging
import os
import signal
import sys
from prometheus_client import start_http_server, Counter

# Configuration
LOG_FILE = os.getenv('ARPWATCH_LOG_FILE', '/var/log/arpwatch.log')
METRICS_PORT = int(os.getenv('METRICS_PORT', '8000'))
METRICS_ADDR = os.getenv('METRICS_ADDR', '0.0.0.0')

# Patterns and metrics
NEW_STATION = re.compile(r'new station', re.IGNORECASE)
counter = Counter('arpwatch_new_station_total', 'Total new stations detected')

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

                if NEW_STATION.search(line):
                    counter.inc()
                    logger.debug(f"New station detected: {line}")

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
