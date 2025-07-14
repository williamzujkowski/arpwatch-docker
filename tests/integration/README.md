# Integration Testing Guide for arpwatch-docker

This guide provides comprehensive patterns and examples for implementing integration tests for the arpwatch-docker project using testcontainers-python.

## Overview

The arpwatch-docker project consists of:
- An arpwatch container that monitors network traffic (using `network_mode: host`)
- A Prometheus metrics exporter that exposes metrics on port 8000
- A Prometheus server that scrapes the metrics
- Log file monitoring and metrics generation

## Key Testing Challenges

1. **Network Mode Host**: The arpwatch container uses `network_mode: host` which is Linux-only and presents challenges for cross-platform testing
2. **Log File Monitoring**: The exporter monitors `/var/log/arpwatch.log` for events
3. **Metrics Validation**: Need to verify Prometheus metrics are exposed correctly
4. **Multi-Container Orchestration**: Testing the interaction between arpwatch, exporter, and Prometheus

## Recommended Testing Architecture

### 1. Use Bridge Networking for Tests

Instead of `network_mode: host`, use bridge networking with explicit port mapping for better test isolation and cross-platform compatibility:

```python
# tests/conftest.py
import pytest
from testcontainers.compose import DockerCompose
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
import os
import time

@pytest.fixture(scope="session")
def test_compose_file():
    """Create a test-specific docker-compose configuration"""
    test_compose = """
version: '3.8'
services:
  arpwatch:
    build:
      context: ../..
      dockerfile: Dockerfile
    environment:
      - IFACE=eth0  # Use container's eth0 instead of host interface
    volumes:
      - arpwatch-data:/var/lib/arpwatch
      - arpwatch-logs:/var/log
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/metrics"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090"
    volumes:
      - ./prometheus-test.yml:/etc/prometheus/prometheus.yml:ro
    depends_on:
      arpwatch:
        condition: service_healthy

volumes:
  arpwatch-data:
  arpwatch-logs:
"""
    
    # Write test compose file
    os.makedirs("tests/integration", exist_ok=True)
    with open("tests/integration/docker-compose.test.yml", "w") as f:
        f.write(test_compose)
    
    yield "tests/integration/docker-compose.test.yml"
    
    # Cleanup
    os.remove("tests/integration/docker-compose.test.yml")
```

### 2. Container Fixtures with Proper Lifecycle Management

```python
# tests/conftest.py (continued)

@pytest.fixture(scope="module")
def docker_services(test_compose_file):
    """Start all services using docker-compose"""
    compose = DockerCompose(
        filepath=os.path.dirname(test_compose_file),
        compose_file_name=os.path.basename(test_compose_file),
        pull=True
    )
    
    with compose:
        # Wait for services to be ready
        compose.wait_for(r"Metrics server started")
        yield compose

@pytest.fixture(scope="module")
def arpwatch_container():
    """Individual arpwatch container for focused testing"""
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    container.with_volume_mapping("/tmp/test-logs", "/var/log", "rw")
    container.with_exposed_ports(8000)
    
    with container:
        # Wait for metrics endpoint to be ready
        wait_for_http_endpoint(container, 8000, "/metrics")
        yield container

def wait_for_http_endpoint(container, port, path="/", timeout=30):
    """Wait for HTTP endpoint to respond with 200 OK"""
    import requests
    from time import sleep
    
    start_time = time.time()
    mapped_port = container.get_exposed_port(port)
    url = f"http://localhost:{mapped_port}{path}"
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == 200:
                return
        except requests.exceptions.RequestException:
            pass
        sleep(0.5)
    
    raise TimeoutError(f"HTTP endpoint {url} did not respond within {timeout}s")
```

### 3. Testing Patterns

#### Pattern 1: Container Startup and Health Checks

```python
# tests/test_container_health.py
import pytest
import requests
from testcontainers.core.container import DockerContainer

def test_arpwatch_container_starts_successfully(arpwatch_container):
    """Test that arpwatch container starts and becomes healthy"""
    assert arpwatch_container.get_container_host_ip()
    
    # Check container is running
    container_state = arpwatch_container.get_wrapped_container().attrs['State']
    assert container_state['Running'] is True
    
    # Verify health check passes
    health = container_state.get('Health', {})
    assert health.get('Status') in ['healthy', 'starting']

def test_metrics_endpoint_responds(arpwatch_container):
    """Test that metrics endpoint is accessible"""
    port = arpwatch_container.get_exposed_port(8000)
    response = requests.get(f"http://localhost:{port}/metrics")
    
    assert response.status_code == 200
    assert "arpwatch_new_station_total" in response.text
    assert response.headers.get('Content-Type') == 'text/plain; version=0.0.4; charset=utf-8'
```

#### Pattern 2: Log File Injection and Monitoring

```python
# tests/test_log_monitoring.py
import time
import docker
from datetime import datetime

def test_log_injection_triggers_metrics(arpwatch_container):
    """Test that injecting log entries updates metrics"""
    # Get initial metric value
    port = arpwatch_container.get_exposed_port(8000)
    initial_metrics = requests.get(f"http://localhost:{port}/metrics").text
    initial_count = parse_metric_value(initial_metrics, "arpwatch_new_station_total")
    
    # Inject test log entry
    container_id = arpwatch_container.get_wrapped_container().id
    client = docker.from_env()
    
    # Execute command to append to log file inside container
    timestamp = datetime.now().strftime("%b %d %H:%M:%S")
    log_entry = f"{timestamp} arpwatch: new station 192.168.1.100 aa:bb:cc:dd:ee:ff eth0\\n"
    
    exec_result = client.containers.get(container_id).exec_run(
        f"/bin/sh -c 'echo \"{log_entry}\" >> /var/log/arpwatch.log'",
        user='root'
    )
    assert exec_result.exit_code == 0
    
    # Wait for metric to update
    time.sleep(1)
    
    # Verify metric increased
    updated_metrics = requests.get(f"http://localhost:{port}/metrics").text
    updated_count = parse_metric_value(updated_metrics, "arpwatch_new_station_total")
    assert updated_count == initial_count + 1

def parse_metric_value(metrics_text, metric_name):
    """Parse metric value from Prometheus text format"""
    for line in metrics_text.split('\n'):
        if line.startswith(metric_name) and not line.startswith('#'):
            return float(line.split()[-1])
    return 0.0
```

#### Pattern 3: Multi-Container Integration Testing

```python
# tests/test_prometheus_integration.py
import time
import requests
from urllib.parse import quote

def test_prometheus_scrapes_arpwatch_metrics(docker_services):
    """Test full integration with Prometheus scraping"""
    # Wait for Prometheus to start and scrape
    time.sleep(10)
    
    # Get Prometheus port
    prometheus_port = docker_services.get_service_port("prometheus", 9090)
    
    # Query Prometheus for arpwatch metrics
    query = quote("arpwatch_new_station_total")
    prometheus_url = f"http://localhost:{prometheus_port}/api/v1/query?query={query}"
    
    response = requests.get(prometheus_url)
    assert response.status_code == 200
    
    data = response.json()
    assert data['status'] == 'success'
    assert len(data['data']['result']) > 0
    
    # Verify metric has been scraped
    result = data['data']['result'][0]
    assert result['metric']['__name__'] == 'arpwatch_new_station_total'
    assert 'value' in result

def test_prometheus_targets_health(docker_services):
    """Test that Prometheus successfully connects to arpwatch target"""
    prometheus_port = docker_services.get_service_port("prometheus", 9090)
    
    # Check targets endpoint
    response = requests.get(f"http://localhost:{prometheus_port}/api/v1/targets")
    assert response.status_code == 200
    
    targets = response.json()['data']['activeTargets']
    arpwatch_target = next((t for t in targets if 'arpwatch' in t['labels'].get('job', '')), None)
    
    assert arpwatch_target is not None
    assert arpwatch_target['health'] == 'up'
```

#### Pattern 4: Volume Mount Testing

```python
# tests/test_data_persistence.py
import tempfile
import os

def test_arpwatch_data_persistence():
    """Test that arpwatch data persists across container restarts"""
    with tempfile.TemporaryDirectory() as tmpdir:
        # First container run
        container1 = DockerContainer("arpwatch:test")
        container1.with_volume_mapping(tmpdir, "/var/lib/arpwatch", "rw")
        container1.with_env("IFACE", "eth0")
        
        with container1:
            # Simulate some activity
            time.sleep(5)
            
            # Check that data files were created
            container1.exec("ls -la /var/lib/arpwatch/")
        
        # Verify files exist on host
        assert os.path.exists(os.path.join(tmpdir, "arp.dat"))
        
        # Second container run with same volume
        container2 = DockerContainer("arpwatch:test")
        container2.with_volume_mapping(tmpdir, "/var/lib/arpwatch", "rw")
        container2.with_env("IFACE", "eth0")
        
        with container2:
            # Verify data files still exist
            result = container2.exec("cat /var/lib/arpwatch/arp.dat")
            assert result.exit_code == 0
```

### 4. CI/CD Integration with GitHub Actions

```yaml
# .github/workflows/integration-tests.yml
name: Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'
    
    - name: Install dependencies
      run: |
        pip install pytest pytest-timeout testcontainers[docker] requests
    
    - name: Build Docker image
      run: docker build -t arpwatch:test .
    
    - name: Run integration tests
      run: |
        pytest tests/integration/ -v --timeout=300
      env:
        DOCKER_BUILDKIT: 1
        TESTCONTAINERS_RYUK_DISABLED: "true"  # Disable Ryuk for CI
    
    - name: Upload test results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: test-results
        path: test-results.xml
```

### 5. Advanced Testing Patterns

#### Pattern 5: Network Traffic Simulation

```python
# tests/test_network_simulation.py
from scapy.all import ARP, Ether, sendp
import subprocess

def test_arp_packet_detection(arpwatch_container):
    """Test that arpwatch detects simulated ARP packets"""
    # Note: This requires the test to run with appropriate permissions
    # and is more suitable for dedicated test environments
    
    # Get container network namespace
    container_id = arpwatch_container.get_wrapped_container().id
    
    # Create test ARP packet
    arp_packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(
        op="who-has",
        hwsrc="aa:bb:cc:dd:ee:ff",
        psrc="192.168.1.100",
        pdst="192.168.1.1"
    )
    
    # Send packet (requires root/sudo in real environment)
    # This is pseudo-code for illustration
    # sendp(arp_packet, iface="docker0", verbose=False)
    
    # Wait and check metrics
    time.sleep(2)
    
    # Verify detection in metrics
    port = arpwatch_container.get_exposed_port(8000)
    response = requests.get(f"http://localhost:{port}/metrics")
    assert "arpwatch_new_station_total" in response.text
```

#### Pattern 6: Performance and Load Testing

```python
# tests/test_performance.py
import concurrent.futures
import time

def test_metrics_endpoint_under_load(arpwatch_container):
    """Test metrics endpoint performance under concurrent requests"""
    port = arpwatch_container.get_exposed_port(8000)
    url = f"http://localhost:{port}/metrics"
    
    def make_request():
        start = time.time()
        response = requests.get(url)
        duration = time.time() - start
        return response.status_code, duration
    
    # Make 100 concurrent requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(make_request) for _ in range(100)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    # Verify all requests succeeded
    status_codes = [r[0] for r in results]
    assert all(code == 200 for code in status_codes)
    
    # Verify response times are reasonable
    durations = [r[1] for r in results]
    avg_duration = sum(durations) / len(durations)
    assert avg_duration < 0.1  # Average response under 100ms
```

## Best Practices

1. **Container Lifecycle Management**
   - Use pytest fixtures with appropriate scopes (session, module, function)
   - Always implement proper cleanup with finalizers
   - Use context managers for automatic resource cleanup

2. **Network Configuration**
   - Avoid `network_mode: host` in tests for better portability
   - Use dynamic port mapping to avoid conflicts
   - Create custom Docker networks for multi-container tests

3. **Wait Strategies**
   - Implement robust wait strategies for container readiness
   - Use health checks in docker-compose
   - Wait for specific log messages or HTTP endpoints

4. **Test Data Management**
   - Use temporary directories for test volumes
   - Clean up test data after each test
   - Implement data fixtures for consistent test scenarios

5. **CI/CD Considerations**
   - Disable Testcontainers Ryuk in CI environments
   - Use appropriate timeouts for container operations
   - Cache Docker images when possible
   - Run tests in parallel with proper isolation

## Common Pitfalls and Solutions

1. **Port Conflicts**
   - Solution: Always use dynamic port mapping via testcontainers

2. **Container Startup Failures**
   - Solution: Implement comprehensive health checks and wait strategies

3. **Flaky Tests**
   - Solution: Add proper waits and retries for eventual consistency

4. **Resource Cleanup**
   - Solution: Use pytest fixtures with finalizers and context managers

5. **Cross-Platform Issues**
   - Solution: Avoid host networking, use bridge mode with port mapping

## Example Test Suite Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── integration/
│   ├── __init__.py
│   ├── test_container_health.py
│   ├── test_log_monitoring.py
│   ├── test_metrics.py
│   ├── test_prometheus_integration.py
│   └── docker-compose.test.yml
├── unit/
│   ├── __init__.py
│   └── test_metrics_exporter.py
└── performance/
    ├── __init__.py
    └── test_load.py
```

## Running the Tests

```bash
# Install dependencies
pip install -r tests/requirements.txt

# Run all integration tests
pytest tests/integration/ -v

# Run with coverage
pytest tests/integration/ --cov=exporter --cov-report=html

# Run specific test
pytest tests/integration/test_metrics.py::test_metrics_endpoint_responds -v

# Run with increased timeout for slow containers
pytest tests/integration/ --timeout=300
```

## Conclusion

This testing approach provides:
- Reliable, reproducible integration tests
- Cross-platform compatibility
- Good test isolation
- Clear patterns for common testing scenarios
- Easy CI/CD integration

The key is to balance realistic testing (as close to production as possible) with test reliability and maintainability. Using testcontainers-python provides the best of both worlds.