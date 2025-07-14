"""
Basic example of using testcontainers-python for arpwatch-docker integration testing.
This file demonstrates the simplest patterns for getting started.
"""
import pytest
import requests
import time
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs


@pytest.mark.integration
def test_simple_container_startup():
    """
    Simplest example: Start container and check if it's running.
    """
    # Create container instance
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    container.with_exposed_ports(8000)
    
    # Start container using context manager (auto-cleanup)
    with container:
        # Check container is running
        assert container.get_wrapped_container().status == "running"
        
        # Get mapped port
        metrics_port = container.get_exposed_port(8000)
        print(f"Metrics available at: http://localhost:{metrics_port}/metrics")
        
        # Give container time to start up
        time.sleep(5)
        
        # Check metrics endpoint
        response = requests.get(f"http://localhost:{metrics_port}/metrics")
        assert response.status_code == 200


@pytest.mark.integration
def test_wait_for_container_logs():
    """
    Example: Wait for specific log message before proceeding.
    """
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    
    with container:
        # Wait for specific log message indicating startup
        wait_for_logs(container, "Metrics server started", timeout=30)
        
        # Now we know the service is ready
        logs = container.get_logs().decode('utf-8')
        assert "Metrics server started" in logs


@pytest.mark.integration
def test_inject_test_data():
    """
    Example: Inject test data and verify metrics update.
    """
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    container.with_exposed_ports(8000)
    
    with container:
        # Wait for container to be ready
        time.sleep(5)
        
        # Get metrics endpoint
        metrics_port = container.get_exposed_port(8000)
        
        # Check initial metric value
        response = requests.get(f"http://localhost:{metrics_port}/metrics")
        initial_text = response.text
        
        # Extract metric value (simplified parsing)
        initial_value = 0
        for line in initial_text.split('\n'):
            if line.startswith('arpwatch_new_station_total') and not line.startswith('#'):
                initial_value = float(line.split()[-1])
                break
        
        # Inject a log entry
        container.exec(
            "sh -c 'echo \"Jan 01 12:00:00 arpwatch: new station 192.168.1.100 aa:bb:cc:dd:ee:ff eth0\" >> /var/log/arpwatch.log'"
        )
        
        # Wait for metric to update
        time.sleep(2)
        
        # Check updated metric
        response = requests.get(f"http://localhost:{metrics_port}/metrics")
        updated_text = response.text
        
        # Verify metric increased
        updated_value = 0
        for line in updated_text.split('\n'):
            if line.startswith('arpwatch_new_station_total') and not line.startswith('#'):
                updated_value = float(line.split()[-1])
                break
        
        assert updated_value > initial_value


@pytest.mark.integration
def test_custom_wait_strategy():
    """
    Example: Custom wait strategy for container readiness.
    """
    def wait_for_metrics_endpoint(container: DockerContainer, timeout: int = 30):
        """Custom wait function for metrics endpoint."""
        start_time = time.time()
        port = container.get_exposed_port(8000)
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"http://localhost:{port}/metrics", timeout=1)
                if response.status_code == 200 and "arpwatch_new_station_total" in response.text:
                    return True
            except:
                pass
            time.sleep(0.5)
        
        raise TimeoutError("Metrics endpoint did not become ready")
    
    # Use the custom wait strategy
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    container.with_exposed_ports(8000)
    
    with container:
        # Wait using custom strategy
        wait_for_metrics_endpoint(container)
        
        # Now we're sure the metrics endpoint is ready
        port = container.get_exposed_port(8000)
        response = requests.get(f"http://localhost:{port}/metrics")
        assert response.status_code == 200
        assert "arpwatch_new_station_total" in response.text


@pytest.mark.integration
def test_multiple_containers_interaction():
    """
    Example: Test interaction between multiple containers.
    """
    # Create a custom network
    import docker
    client = docker.from_env()
    network = client.networks.create("test-network", driver="bridge")
    
    try:
        # Start arpwatch container
        arpwatch = DockerContainer("arpwatch:test")
        arpwatch.with_name("arpwatch-test")
        arpwatch.with_env("IFACE", "eth0")
        arpwatch.with_exposed_ports(8000)
        arpwatch.with_network(network.name)
        arpwatch.with_network_aliases("arpwatch")
        
        # Start a test client container
        client_container = DockerContainer("alpine:latest")
        client_container.with_network(network.name)
        client_container.with_command("sleep 3600")
        
        with arpwatch, client_container:
            # Wait for arpwatch to be ready
            time.sleep(5)
            
            # Test connectivity from client to arpwatch
            result = client_container.exec("wget -qO- http://arpwatch:8000/metrics")
            assert result.exit_code == 0
            assert "arpwatch_new_station_total" in result.output.decode()
            
    finally:
        # Clean up network
        network.remove()


@pytest.mark.integration
@pytest.mark.parametrize("log_entry,should_increment", [
    ("new station 192.168.1.1 aa:bb:cc:dd:ee:ff eth0", True),
    ("changed ethernet address 192.168.1.2", False),
    ("flip flop 192.168.1.3", False),
    ("NEW STATION 192.168.1.4 aa:bb:cc:dd:ee:ff eth0", True),  # Case insensitive
])
def test_log_pattern_parametrized(log_entry: str, should_increment: bool):
    """
    Example: Parametrized test for different log patterns.
    """
    container = DockerContainer("arpwatch:test")
    container.with_env("IFACE", "eth0")
    container.with_exposed_ports(8000)
    
    with container:
        # Wait for startup
        time.sleep(5)
        
        port = container.get_exposed_port(8000)
        
        # Get initial count
        response = requests.get(f"http://localhost:{port}/metrics")
        initial_count = 0
        for line in response.text.split('\n'):
            if line.startswith('arpwatch_new_station_total') and not line.startswith('#'):
                initial_count = float(line.split()[-1])
                break
        
        # Inject log entry
        full_log = f"Jan 01 12:00:00 arpwatch: {log_entry}"
        container.exec(f"sh -c 'echo \"{full_log}\" >> /var/log/arpwatch.log'")
        
        # Wait for processing
        time.sleep(2)
        
        # Check if metric changed
        response = requests.get(f"http://localhost:{port}/metrics")
        final_count = 0
        for line in response.text.split('\n'):
            if line.startswith('arpwatch_new_station_total') and not line.startswith('#'):
                final_count = float(line.split()[-1])
                break
        
        if should_increment:
            assert final_count > initial_count, f"Expected increment for: {log_entry}"
        else:
            assert final_count == initial_count, f"Unexpected increment for: {log_entry}"


# Helper function that can be used in tests
def get_metric_value(metrics_text: str, metric_name: str) -> float:
    """Extract metric value from Prometheus format text."""
    for line in metrics_text.split('\n'):
        if line.startswith(metric_name) and not line.startswith('#'):
            # Handle metrics with or without labels
            if '{' in line:
                # Metric with labels: metric_name{label="value"} 123
                value_part = line.split('}')[-1].strip()
            else:
                # Simple metric: metric_name 123
                value_part = line.split()[-1]
            return float(value_part)
    return 0.0


if __name__ == "__main__":
    # Allow running individual tests directly
    pytest.main([__file__, "-v"])