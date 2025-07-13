#!/usr/bin/env python3
import re
import time
from prometheus_client import start_http_server, Counter

LOG_FILE = '/var/log/arpwatch.log'
NEW_STATION = re.compile(r'new station', re.IGNORECASE)
counter = Counter('arpwatch_new_station_total', 'Total new stations detected')

def follow(f):
    f.seek(0, 2)
    while True:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue
        yield line

if __name__ == '__main__':
    # Bind metrics server on all interfaces
    start_http_server(8000, addr='0.0.0.0')   # Explicit bind to 0.0.0.0 :contentReference[oaicite:4]{index=4}
    with open(LOG_FILE, 'r') as logfile:
        for line in follow(logfile):
            if NEW_STATION.search(line):
                counter.inc()
