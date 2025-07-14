# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a containerized network monitoring solution designed for **code-generation LLM** implementation that:

- **Builds arpwatch from source** on Ubuntu 24.04 LTS in a multi-stage Docker container
- **Fetches and compiles IEEE OUI database** for vendor lookups, avoiding HTTP 418 errors
- **Exposes Prometheus metrics** via a custom Python exporter that tails arpwatch logs
- **Orchestrates services** with Docker Compose including health checks and monitoring
- **Sends email alerts** via nullmailer for new network device detection

**Target**: Self-contained network monitoring with full LAN visibility using `network_mode: host`

## Key Commands

### Development and Build
```bash
# Build and run the entire stack
docker-compose up -d --build

# View logs
docker-compose logs -f arpwatch

# Stop services
docker-compose down

# Rebuild just the arpwatch image
docker build -t arpwatch:latest .
```

### Testing and Validation
```bash
# Run complete test suite
pytest

# Run unit tests only
pytest tests/unit/ -v

# Run integration tests (requires Docker)
pytest tests/integration/ -v

# Run tests with coverage
pytest --cov=exporter --cov-report=html

# Run specific test categories
pytest tests/unit/test_metrics_exporter.py::TestRegexPatterns -v

# Check if metrics exporter is working
curl http://localhost:8000/metrics | grep arpwatch_new_station_total

# View Prometheus UI
# Navigate to http://localhost:9090

# Check container health and validate Docker configuration
docker-compose ps
docker-compose config

# Quality gates (automatically run in CI)
shellcheck cmd.sh                    # Shell script validation
hadolint Dockerfile                  # Dockerfile linting
python3 -m py_compile exporter/metrics_exporter.py  # Python syntax check

# Email optional testing
docker-compose up -d --build         # Test without email config
ARPWATCH_NOTIFICATION_EMAIL_TO=test@example.com docker-compose up  # Test with email
```

### Debugging
```bash
# Access container shell
docker-compose exec arpwatch bash

# Check arpwatch logs inside container
docker-compose exec arpwatch tail -f /var/log/arpwatch.log

# Verify arpwatch process
docker-compose exec arpwatch ps aux | grep arpwatch
```

## Architecture and Key Components

### Implementation Blueprint (from project_plan.md)

**Repository Structure:**
```
/
├── Dockerfile              # Multi-stage: compile arpwatch, build ethercodes, runtime
├── Dockerfile.crossbuild   # Cross-compilation support (if needed)
├── cmd.sh                  # Entrypoint: init logs, start rsyslog, launch exporter, run arpwatch
├── exporter/
│   └── metrics_exporter.py # Python prometheus_client + watchdog log tailer
├── prometheus/
│   └── prometheus.yml      # Scrape configuration for exporter
└── docker-compose.yml      # Orchestration: arpwatch + prometheus services
```

### Core Pipeline
1. **arpwatch** (compiled from arpwatch-2.1a15) monitors network → detects new MAC addresses
2. **rsyslog** captures arpwatch output → writes to `/var/log/arpwatch.log`
3. **metrics_exporter.py** implements `follow()` tail logic → increments `arpwatch_new_station_total` Counter
4. **Prometheus** scrapes metrics from `0.0.0.0:8000` (bound on all interfaces)

### Critical Components

#### Arpwatch Build & Install
- Ubuntu 24.04 base with `build-essential`, `autoconf`, `automake`, `libpcap-dev`
- Downloads and compiles `arpwatch-2.1a15` to `/usr/local/sbin/arpwatch`
- Multi-stage build separates compile-time from runtime dependencies

#### Ethercodes Database
- Downloads `oui.csv` over HTTPS from IEEE
- Uses `fetch_ethercodes.py -k` to generate `/ethercodes.dat` (avoids HTTP 418 errors)
- Enables vendor lookups for detected MAC addresses

#### Prometheus Exporter Details
- **File**: `exporter/metrics_exporter.py`
- **Port**: 8000 (bound to `0.0.0.0` for container accessibility)
- **Metric**: `arpwatch_new_station_total` (Counter type)
- **Pattern**: `re.compile(r'new station', re.IGNORECASE)`
- **Method**: Implements `follow()` function for efficient log tailing

#### Container Orchestration
- **arpwatch service**: `network_mode: host` for full LAN visibility
- **Health check**: `wget -qO- http://localhost:8000/metrics` every 30s
- **prometheus service**: Official `prom/prometheus` image with mounted config

### Security Model
- Runs as non-root `arpwatch` user with `--no-create-home --shell /usr/sbin/nologin`
- Uses `network_mode: host` (required for network monitoring)
- Drops all Linux capabilities except NET_RAW
- Minimal attack surface with Ubuntu 24.04 base image
- Explicit ownership: `chown arpwatch:arpwatch /var/log/arpwatch.log /var/lib/arpwatch`

## Development Standards & Quality Gates

### Shell Scripts (Quality Gate: ShellCheck)
- **Required**: `set -euo pipefail` at the top of all shell scripts
- **Required**: Pass ShellCheck validation before commits
- Use explicit variable expansion: `"${VAR}"` not `$VAR`
- Validate required environment variables with `: "${VAR:?Missing VAR}"`

### Docker (Quality Gate: hadolint)
- **Multi-stage builds** to minimize image size and separate build/runtime
- **Pin base image versions** explicitly (e.g., `ubuntu:24.04`, not `ubuntu:latest`)
- **Clean apt cache**: `rm -rf /var/lib/apt/lists/*` after package installation
- **Run as non-root user**: Create dedicated user with `--no-create-home --shell /usr/sbin/nologin`
- **Security**: Drop all Linux capabilities except `NET_RAW`

### Python (Exporter Standards)
- Compatible with **Python 3** (system python3 in Ubuntu 24.04)
- Use **prometheus_client** library for metrics (`Counter`, `Gauge`, `Histogram`)
- Use **watchdog** library for efficient file monitoring (optional enhancement)
- **Memory efficiency**: Implement `follow()` tail logic to avoid loading entire log files
- **Binding**: Use `start_http_server(8000, addr='0.0.0.0')` for container accessibility

### Container Configuration
- **Network mode**: `network_mode: host` required for arpwatch network monitoring
- **Health checks**: HTTP endpoint validation every 30s with `wget -qO-`
- **Restart policy**: `unless-stopped` for production stability
- **Volume persistence**: Mount `/var/lib/arpwatch` for data persistence

### Environment Variables
**Optional**:
- `ARPWATCH_NOTIFICATION_EMAIL_TO` - Alert destination email (if not set, email alerts disabled)
- `ARPWATCH_NOTIFICATION_EMAIL_FROM` - From address for alerts (required if EMAIL_TO is set)
- `ARPWATCH_NOTIFICATION_EMAIL_SERVER` - SMTP server for email delivery (required if EMAIL_TO is set)
- `ARPWATCH_INTERFACE` - Specific interface to monitor (defaults to all interfaces)

**Email Configuration Logic**:
- If `ARPWATCH_NOTIFICATION_EMAIL_TO` is not set, arpwatch runs without email notifications
- If `ARPWATCH_NOTIFICATION_EMAIL_TO` is set, then `ARPWATCH_NOTIFICATION_EMAIL_FROM` and `ARPWATCH_NOTIFICATION_EMAIL_SERVER` become required

**✅ Implementation Completed**: 
Email configuration is now fully optional. If `ARPWATCH_NOTIFICATION_EMAIL_TO` is not set, arpwatch runs without email notifications. When set, `ARPWATCH_NOTIFICATION_EMAIL_FROM` and `ARPWATCH_NOTIFICATION_EMAIL_SERVER` become required.

## Implementation Status & Recent Updates

### ✅ **Completed Improvements (2025-01-13)**

**Phase 1: Email Optional & Quality Gates**
- **Email configuration made optional**: Modified `cmd.sh` to allow operation without email settings
- **Quality gates implemented**: Added ShellCheck and hadolint validation to CI workflow  
- **CI passing**: All quality gates validate successfully

**Phase 2: Unit Testing Infrastructure**
- **Comprehensive pytest framework**: 8 unit tests covering core functionality
- **Coverage reporting**: Integrated with CI, 80% threshold configured
- **Test categories**: Follow function, regex patterns, Prometheus metrics, integrated workflow

**Phase 3: Integration Testing with Testcontainers**
- **Full testcontainers suite**: End-to-end Docker pipeline validation
- **Multiple test scenarios**: Container health, log injection, metric validation
- **CI-ready**: Configured for both local development and GitHub Actions

### 🔧 **Key Implementation Learnings**

**Email Configuration Pattern:**
```bash
# Conditional validation in cmd.sh:12-14
if [[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]]; then
    : "${ARPWATCH_NOTIFICATION_EMAIL_FROM:?Missing when EMAIL_TO is set}"
    : "${ARPWATCH_NOTIFICATION_EMAIL_SERVER:?Missing when EMAIL_TO is set}"
    echo "Email notifications enabled for: ${ARPWATCH_NOTIFICATION_EMAIL_TO}"
else
    echo "Email notifications disabled - no ARPWATCH_NOTIFICATION_EMAIL_TO configured"
fi
```

**Quality Gates Configuration:**
- **ShellCheck**: Validates shell script quality, catches common issues
- **hadolint**: Dockerfile linting with `failure-threshold: error` (allows warnings)
- **Integration**: Both run in parallel with early feedback

**Testing Architecture:**
- **Unit tests**: Fast validation of core logic (8 tests, ~4s execution)
- **Integration tests**: Full Docker pipeline with testcontainers
- **Coverage**: Comprehensive metrics validation and log processing tests

## Testing Strategy (Enhanced Implementation)

### 1. Unit Tests for Exporter
**Required Test Coverage:**
- **Test `follow()` function**: Feed sample log file, append lines, assert "new station" increments Counter
- **Test Regex patterns**: Verify `re.compile(r'new station', re.IGNORECASE)` matches known variations
- **Framework**: Use pytest for Python testing

### 2. Integration Tests
**Container Validation:**
- **Docker Build**: Run `docker-compose config` and `docker build --target builder` to catch syntax/dependency issues
- **Full Pipeline**: Use `testcontainers` library to launch arpwatch service, inject "new station" entry to log, curl exporter endpoint, assert metric appears
- **Health Checks**: Verify `wget -qO- http://localhost:8000/metrics` succeeds

### 3. LLM-Driven Code-Gen Verification
**For Code Generation Quality:**
- **Prompt Tests**: Use fixed prompts to generate each artifact (Dockerfile, Compose YAML, exporter code)
- **Diff Checks**: Compare LLM-generated files against project_plan.md canonical examples
- **Regression Testing**: After prompt/model updates, rerun generation and diff for consistency

## Common Development Tasks

### Adding New Metrics
1. Edit `exporter/metrics_exporter.py`
2. Add new Counter/Gauge/Histogram from prometheus_client
3. Update regex patterns or add new log parsing logic
4. **Test**: `curl http://localhost:8000/metrics | grep your_new_metric`
5. **Validate**: Ensure metric appears in Prometheus UI at http://localhost:9090

### Modifying Email Alerts
- Email configuration handled by **nullmailer** (installed in runtime container)
- Arpwatch sends to address in `ARPWATCH_NOTIFICATION_EMAIL_TO`
- **Custom behavior**: Modify nullmailer config in Dockerfile runtime stage
- **Testing**: Check `/var/log/mail.log` inside container for delivery status

### Making Email Configuration Optional
**Current Issue**: `cmd.sh:12-14` requires all email variables to be set

**To implement optional email**:
1. **Modify cmd.sh validation logic**:
   ```bash
   # Replace lines 12-14 with conditional validation
   if [[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]]; then
       : "${ARPWATCH_NOTIFICATION_EMAIL_FROM:?Missing ARPWATCH_NOTIFICATION_EMAIL_FROM when EMAIL_TO is set}"
       : "${ARPWATCH_NOTIFICATION_EMAIL_SERVER:?Missing ARPWATCH_NOTIFICATION_EMAIL_SERVER when EMAIL_TO is set}"
   fi
   ```

2. **Modify arpwatch command building**:
   ```bash
   # Update CMD_ARGS building (around line 26)
   CMD_ARGS=(-u arpwatch -a -p)
   [[ -n "${ARPWATCH_INTERFACE:-}" ]] && CMD_ARGS+=(-i "$ARPWATCH_INTERFACE")
   [[ -n "${ARPWATCH_NOTIFICATION_EMAIL_TO:-}" ]] && CMD_ARGS+=(-m "$ARPWATCH_NOTIFICATION_EMAIL_TO")
   ```

3. **Update .env.example** to show email vars as optional with comments

### Updating arpwatch Version
1. **Change version** in `Dockerfile` line 11: `wget --no-verbose https://ee.lbl.gov/downloads/arpwatch/arpwatch-X.Y.Z.tar.gz`
2. **Test build**: `docker build -t arpwatch:test .`
3. **Integration test**: Run full docker-compose stack, verify functionality
4. **Quality gates**: Run shellcheck and hadolint before committing

### Cross-Platform Builds
- Use `Dockerfile.crossbuild` for cross-compilation support if needed
- Multi-arch builds: `docker buildx build --platform linux/amd64,linux/arm64`

## Quality Gates & CI/CD

**Automated Checks (Required before merge):**
- **Linting**: ShellCheck on `cmd.sh`, hadolint on Dockerfiles
- **Security**: Verify non-root execution, capability dropping
- **Documentation**: Concise comments in Dockerfiles and scripts
- **Build validation**: `docker-compose config` and successful container startup
- **Integration**: Full pipeline test with metric validation

**GitHub Actions Workflows**:
- **Main CI** (`.github/workflows/ci.yml`): Quality gates, unit tests, linting with coverage reporting
- **Integration Tests** (`.github/workflows/integration-tests.yml`): Testcontainers-based full pipeline validation
- **CodeQL Analysis**: Automated security scanning

**Current CI Status**: ✅ All main workflows passing
- Quality gates: ShellCheck + hadolint validation
- Unit tests: 8 tests with coverage reporting  
- Lint validation: Super-linter with comprehensive checks
- Coverage artifacts: HTML and XML reports generated