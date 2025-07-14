"""
Pytest configuration and shared fixtures for arpwatch-docker integration tests.
"""
import os
import pytest
import tempfile
import time
import yaml
from pathlib import Path
from typing import Generator, Dict, Any

import docker
import requests
from testcontainers.core.container import DockerContainer
from testcontainers.compose import DockerCompose


# Get project root directory
PROJECT_ROOT = Path(__file__).parent.parent


@pytest.fixture(scope="session")
def docker_client() -> docker.DockerClient:
    """Provide Docker client instance."""
    return docker.from_env()


@pytest.fixture(scope="session")
def test_prometheus_config() -> Generator[str, None, None]:
    """Create test Prometheus configuration."""
    prometheus_config = {
        'global': {
            'scrape_interval': '5s',
            'evaluation_interval': '5s'
        },
        'scrape_configs': [
            {
                'job_name': 'prometheus',
                'static_configs': [
                    {'targets': ['localhost:9090']}
                ]
            },
            {
                'job_name': 'arpwatch',
                'static_configs': [
                    {'targets': ['arpwatch:8000']}
                ],
                'scrape_interval': '5s'
            }
        ]
    }
    
    # Create temporary directory for test configs
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, 'prometheus.yml')
        with open(config_path, 'w') as f:
            yaml.dump(prometheus_config, f)
        
        yield config_path


@pytest.fixture(scope="session")
def test_docker_compose_content() -> str:
    """Generate test-specific docker-compose configuration."""
    return """
version: '3.8'

services:
  arpwatch:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: arpwatch-test
    environment:
      - IFACE=eth0
    volumes:
      - arpwatch-data:/var/lib/arpwatch
      - arpwatch-logs:/var/log
    ports:
      - "8000"  # Expose metrics port
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:8000/metrics"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    networks:
      - arpwatch-net
    
  prometheus:
    image: prom/prometheus:latest
    container_name: prometheus-test
    ports:
      - "9090"
    volumes:
      - ./prometheus-test.yml:/etc/prometheus/prometheus.yml:ro
    depends_on:
      arpwatch:
        condition: service_healthy
    networks:
      - arpwatch-net
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/usr/share/prometheus/console_libraries'
      - '--web.console.templates=/usr/share/prometheus/consoles'

networks:
  arpwatch-net:
    driver: bridge

volumes:
  arpwatch-data:
  arpwatch-logs:
"""


@pytest.fixture(scope="module")
def arpwatch_container() -> Generator[DockerContainer, None, None]:
    """
    Start a standalone arpwatch container for testing.
    """
    # Build the image first
    client = docker.from_env()
    image, build_logs = client.images.build(
        path=str(PROJECT_ROOT),
        tag="arpwatch:test",
        rm=True,
        forcerm=True
    )
    
    # Create and start container
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    container.with_exposed_ports(8000)
    
    # Create temporary directory for logs
    with tempfile.TemporaryDirectory() as tmpdir:
        container.with_volume_mapping(tmpdir, "/var/log", "rw")
        
        with container:
            # Wait for container to be ready
            wait_for_http_endpoint(container, 8000, "/metrics")
            yield container


@pytest.fixture(scope="module")
def docker_compose_services(
    test_prometheus_config: str,
    test_docker_compose_content: str
) -> Generator[DockerCompose, None, None]:
    """
    Start all services using docker-compose for integration testing.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        # Write docker-compose file
        compose_file = os.path.join(tmpdir, "docker-compose.test.yml")
        with open(compose_file, "w") as f:
            f.write(test_docker_compose_content)
        
        # Copy prometheus config
        prometheus_test_config = os.path.join(tmpdir, "prometheus-test.yml")
        with open(test_prometheus_config, "r") as src:
            with open(prometheus_test_config, "w") as dst:
                dst.write(src.read())
        
        # Start services
        compose = DockerCompose(
            filepath=tmpdir,
            compose_file_name="docker-compose.test.yml",
            pull=True,
            build=True
        )
        
        with compose:
            # Wait for services to be ready
            time.sleep(10)  # Give services time to start
            
            # TODO: Add more sophisticated health checks
            yield compose


def wait_for_http_endpoint(
    container: DockerContainer,
    port: int,
    path: str = "/",
    timeout: int = 30,
    expected_status: int = 200
) -> None:
    """
    Wait for an HTTP endpoint to respond with expected status code.
    
    Args:
        container: The container to check
        port: The port to check
        path: The HTTP path to check
        timeout: Maximum time to wait in seconds
        expected_status: Expected HTTP status code
    
    Raises:
        TimeoutError: If endpoint doesn't respond within timeout
    """
    start_time = time.time()
    mapped_port = container.get_exposed_port(port)
    url = f"http://localhost:{mapped_port}{path}"
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(url, timeout=1)
            if response.status_code == expected_status:
                return
        except requests.exceptions.RequestException:
            pass
        time.sleep(0.5)
    
    raise TimeoutError(f"HTTP endpoint {url} did not respond with status {expected_status} within {timeout}s")


def parse_prometheus_metric(metrics_text: str, metric_name: str) -> float:
    """
    Parse a specific metric value from Prometheus text format.
    
    Args:
        metrics_text: Raw Prometheus metrics text
        metric_name: Name of the metric to extract
    
    Returns:
        The metric value as a float, or 0.0 if not found
    """
    for line in metrics_text.split('\n'):
        if line.startswith(metric_name) and not line.startswith('#'):
            # Handle metrics with labels
            if '{' in line:
                # Extract value after the closing brace
                parts = line.split('}')
                if len(parts) >= 2:
                    return float(parts[1].strip())
            else:
                # Simple metric without labels
                parts = line.split()
                if len(parts) >= 2:
                    return float(parts[-1])
    return 0.0


@pytest.fixture
def inject_log_entry():
    """
    Fixture to inject log entries into a container.
    """
    def _inject(container: DockerContainer, log_entry: str) -> None:
        """
        Inject a log entry into the container's arpwatch log file.
        
        Args:
            container: The container to inject into
            log_entry: The log entry to inject
        """
        container_id = container.get_wrapped_container().id
        client = docker.from_env()
        
        # Execute command to append to log file inside container
        exec_result = client.containers.get(container_id).exec_run(
            f"/bin/sh -c 'echo \"{log_entry}\" >> /var/log/arpwatch.log'",
            user='root'
        )
        
        if exec_result.exit_code != 0:
            raise RuntimeError(f"Failed to inject log entry: {exec_result.output.decode()}")
    
    return _inject


@pytest.fixture
def wait_for_metric_update():
    """
    Fixture to wait for a metric to update.
    """
    def _wait(
        container: DockerContainer,
        metric_name: str,
        expected_delta: int = 1,
        timeout: int = 10
    ) -> bool:
        """
        Wait for a metric to increase by expected amount.
        
        Args:
            container: The container to check
            metric_name: Name of the metric to monitor
            expected_delta: Expected increase in metric value
            timeout: Maximum time to wait
        
        Returns:
            True if metric updated as expected, False otherwise
        """
        port = container.get_exposed_port(8000)
        url = f"http://localhost:{port}/metrics"
        
        # Get initial value
        response = requests.get(url)
        initial_value = parse_prometheus_metric(response.text, metric_name)
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            response = requests.get(url)
            current_value = parse_prometheus_metric(response.text, metric_name)
            
            if current_value >= initial_value + expected_delta:
                return True
            
            time.sleep(0.5)
        
        return False
    
    return _wait


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "requires_docker: mark test as requiring Docker"
    )