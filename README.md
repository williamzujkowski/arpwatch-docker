# arpwatch-docker

This container builds **arpwatch** from source on Ubuntu 24.04 LTS, fetches the OUI database, runs **nullmailer** for email alerts, and exposes a Prometheus metrics endpoint for new-station alerts.

## Quickstart

1. Copy `.env.example` to `.env` and adjust.
2. Build & launch:
   ```bash
   docker-compose up -d --build
3. View arpwatch alerts via email; metrics at `http://localhost:8000/metrics`; Prometheus UI at `http://localhost:9090`.

## Standards & Practices

* **Shell**: `set -euo pipefail`, ShellCheck-compliant
* **Docker**: Multi-stage, pinned base, apt cache cleanup, non-root user ([Docker Documentation][1])
* **Metrics**: Prometheus exporter increments on “new station” patterns in logs
* **Logging**: rsyslog forwards to Docker logs and file for exporter

---

With this, you have a fully automated, high-quality, standards-compliant Docker setup: building arpwatch yourself, exporting metrics for Prometheus, enforced CI-style healthchecks, and minimal root footprint. Enjoy!

