## Summary

This project packages **arpwatch** into Docker containers, compiles the IEEE OUI database, and exposes network “new station” events via a custom Prometheus exporter, all orchestrated with Docker Compose and monitored in Prometheus ([Atlassian][1]).

---

## Project Overview

1. **Purpose**
   The goal is to build a self-contained network monitoring service that:

   * Runs **arpwatch** in a minimal Ubuntu 24.04 container ([Docker Documentation][2])
   * Fetches and compiles the OUI database for vendor lookups ([Prometheus][3])
   * Implements a Python Prometheus exporter to count “new station” events from `/var/log/arpwatch.log` ([Prometheus][3])
   * Orchestrates services with Docker Compose and provides health checks on the metrics endpoint ([Grafana Labs][4])

2. **Target Audience**
   This plan is written for a **code-generation LLM** to parse and generate all necessary artifacts—Dockerfiles, Compose files, exporter code, and test harnesses—by following explicit, structured instructions ([Example Article of Tely AI][5]).

---

## Implementation Blueprint

### 1. Scaffold & Repository Layout

* `/Dockerfile` – Multi-stage build: compile arpwatch, build ethercodes, and assemble runtime image.
* `/Dockerfile.crossbuild` – Dedicated build image for cross-compilation (if needed).
* `/cmd.sh` – Entrypoint: initialize logs, start rsyslog, launch exporter, then run arpwatch.
* `/exporter/metrics_exporter.py` – Python script using `prometheus_client` and `watchdog` to tail logs and serve metrics on port 8000.
* `/prometheus/prometheus.yml` – Prometheus scrape configuration for the exporter.
* `docker-compose.yml` – Defines `arpwatch` and `prometheus` services, volumes, networking, and healthchecks. ([Grafana Labs][4])

### 2. Key Components

#### 2.1 Arpwatch Build & Install

* Use Ubuntu 24.04 base image and install `build-essential`, `autoconf`, `automake`, `libpcap-dev`, and other dependencies.
* Download and compile `arpwatch-2.1a15`, then `make install` to `/usr/local/sbin/arpwatch`. ([Docker Documentation][2])

#### 2.2 Ethercodes Database

* Download `oui.csv` over HTTPS from the IEEE site.
* Use `fetch_ethercodes.py -k` to generate `/ethercodes.dat` locally, avoiding HTTP 418 errors. ([Prometheus][3])

#### 2.3 Prometheus Exporter

* Implement `follow()` tail logic in Python to read new lines from `/var/log/arpwatch.log`.
* Use `start_http_server(8000, addr='0.0.0.0')` to bind on all interfaces. ([Visual Studio Marketplace][6])
* Expose a `Counter` metric `arpwatch_new_station_total` incremented on each “new station” match.

#### 2.4 Container Orchestration

* Docker Compose service `arpwatch` uses `network_mode: host` for full LAN visibility.
* Healthcheck via `wget -qO- http://localhost:8000/metrics` every 30s. ([Grafana Labs][4])
* Service `prometheus` runs official `prom/prometheus` image with mounted `prometheus.yml`.

---

## Testing Strategy

### 1. Unit Tests for Exporter

* **Test `follow()`**: feed a sample log file, append lines, and assert that new “new station” lines yield increments in the `Counter` ([Medium][7]).
* **Test Regex**: verify that `re.compile(r'new station', IGNORECASE)` matches known variations. ([Medium][7])

### 2. Integration Tests

* **Docker Build Validation**: run `docker-compose config` and `docker build --target builder` to catch syntax or dependency issues ([Grafana Labs][4]).
* **Container Startup**: use a test harness (e.g., `testcontainers` library) to launch `arpwatch` service, write a “new station” entry to `/var/log/arpwatch.log`, then `curl` the exporter endpoint and assert the metric appears. ([Confident AI][8]).

### 3. LLM-Driven Code-Gen Verification

* **Prompt Tests**: Use a set of fixed prompts to generate each artifact (Dockerfile, Compose YAML, exporter code).
* **Diff Checks**: Compare LLM-generated files against this plan’s canonical examples, flagging missing sections or deviations ([arXiv][9]).
* **Regression Testing**: After any prompt or model update, rerun generation and diff to ensure consistency. ([Confident AI][8]).

---

## Quality Gates & Best Practices

* **Linting**: Run **ShellCheck** on `cmd.sh` and **hadolint** on Dockerfiles. ([Example Article of Tely AI][5])
* **Security**: Drop all Linux capabilities except `NET_RAW`, run as non-root.
* **Documentation**: Each Dockerfile and script must include concise comments and usage examples. ([Atlassian][1])
* **CI/CD**: Automate builds, linting, and integration tests in GitHub Actions with workflows under `.github/workflows`.

---

This **project\_plan.md** provides a clear, structured guide for a code-generation LLM to produce a robust, tested, and production-ready **arpwatch-docker** monitoring solution with Prometheus integration.

[1]: https://www.atlassian.com/software/confluence/templates/project-plan?utm_source=chatgpt.com "Project plan - Confluence Templates - Atlassian"
[2]: https://docs.docker.com/engine/daemon/prometheus/?utm_source=chatgpt.com "Collect Docker metrics with Prometheus"
[3]: https://prometheus.io/docs/instrumenting/exporters/?utm_source=chatgpt.com "Exporters and integrations - Prometheus"
[4]: https://grafana.com/docs/grafana-cloud/send-data/metrics/metrics-prometheus/prometheus-config-examples/docker-compose-linux/?utm_source=chatgpt.com "Monitoring a Linux host with Prometheus, Node Exporter ... - Grafana"
[5]: https://examples.tely.ai/best-practices-for-using-llm-for-code-generation-tips-from-experts/?utm_source=chatgpt.com "Best Practices for Using LLM for Code Generation: Tips from Experts"
[6]: https://marketplace.visualstudio.com/items?itemName=maziac.markdown-planner&utm_source=chatgpt.com "Markdown Planner - Visual Studio Marketplace"
[7]: https://medium.com/%40benjamin22-314/automating-test-driven-development-with-llms-c05e7a3cdfe1?utm_source=chatgpt.com "Automating Test Driven Development with LLMs | by Benjamin"
[8]: https://www.confident-ai.com/blog/llm-testing-in-2024-top-methods-and-strategies?utm_source=chatgpt.com "LLM Testing in 2025: Top Methods and Strategies - Confident AI"
[9]: https://arxiv.org/html/2404.10100v1?utm_source=chatgpt.com "LLM-based Test-driven Interactive Code Generation: User ... - arXiv"
