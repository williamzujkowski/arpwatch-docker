#!/usr/bin/env python3
"""
Basic integration tests for arpwatch-docker using testcontainers

Simplified integration tests that validate core functionality:
- Container startup and metrics endpoint
- Basic log injection and metric validation
"""

import pytest
import requests
import time
import docker
from testcontainers.core.container import DockerContainer


class TestBasicIntegration:
    """Basic integration tests for arpwatch container"""
    
    @pytest.fixture(scope="class")
    def docker_image(self):
        """Build the arpwatch Docker image for testing"""
        docker_client = docker.from_env()
        image, logs = docker_client.images.build(
            path=".",
            tag="arpwatch:integration-test",
            dockerfile="Dockerfile",
            rm=True
        )
        yield image
        # Cleanup: remove test image
        try:
            docker_client.images.remove(image.id, force=True)
        except:
            pass
    
    @pytest.fixture(scope="function") 
    def arpwatch_container(self, docker_image):
        """Start arpwatch container for testing"""
        container = DockerContainer("arpwatch:integration-test")
        container.with_exposed_ports(8000)  # Metrics port
        container.with_env("ARPWATCH_NOTIFICATION_EMAIL_TO", "")  # Disable email
        
        with container:
            # Wait for container to start
            time.sleep(10)  # Simple wait strategy
            yield container
    
    def test_container_starts_successfully(self, arpwatch_container):
        """Test that container starts and is accessible"""
        # Verify container is running
        assert arpwatch_container.get_container_host_ip() is not None
        
        # Check logs for successful startup indicators
        logs = arpwatch_container.get_logs().decode('utf-8')
        startup_indicators = [
            "Email notifications disabled",
            "Started Prometheus exporter (pid",
            "Starting Arpwatch Prometheus exporter"
        ]
        assert any(indicator in logs for indicator in startup_indicators), f"No startup indicators found in logs: {logs}"
    
    def test_metrics_endpoint_responds(self, arpwatch_container):
        """Test that Prometheus metrics endpoint is accessible and returns valid data"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Test metrics endpoint with retries
        max_retries = 5
        for attempt in range(max_retries):
            try:
                response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
                if response.status_code == 200:
                    break
                time.sleep(2)
            except requests.exceptions.RequestException:
                if attempt == max_retries - 1:
                    raise
                time.sleep(2)
        
        assert response.status_code == 200
        
        # Verify metrics format
        metrics_text = response.text
        assert "arpwatch_new_station_total" in metrics_text
        assert "# HELP arpwatch_new_station_total" in metrics_text
        assert "# TYPE arpwatch_new_station_total counter" in metrics_text
    
    def test_log_injection_increments_metric(self, arpwatch_container):
        """Test that injecting a log entry increments the metric"""
        host = arpwatch_container.get_container_host_ip() 
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial metric value
        initial_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        initial_value = self._extract_counter_value(initial_response.text, "arpwatch_new_station_total")
        
        # Inject a "new station" log entry
        test_log_entry = "Jan 13 23:50:00 testhost arpwatch: new station 00:11:22:33:44:55 eth0"
        
        # Use container exec to append to log file
        exec_result = arpwatch_container.exec(
            ["sh", "-c", f'echo "{test_log_entry}" >> /var/log/arpwatch.log']
        )
        
        # Wait for metric processing
        time.sleep(5)
        
        # Get updated metric value
        updated_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        updated_value = self._extract_counter_value(updated_response.text, "arpwatch_new_station_total")
        
        # Verify metric incremented
        assert updated_value > initial_value, f"Metric did not increment: {initial_value} -> {updated_value}"
    
    def test_multiple_log_entries(self, arpwatch_container):
        """Test processing multiple different log entries"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial value
        initial_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        initial_value = self._extract_counter_value(initial_response.text, "arpwatch_new_station_total")
        
        # Test entries - mix of valid and invalid
        test_entries = [
            "Jan 13 23:51:00 testhost arpwatch: new station aa:bb:cc:dd:ee:ff eth0",  # Should increment
            "Jan 13 23:51:01 testhost arpwatch: station activity aa:bb:cc:dd:ee:ff eth0",  # Should NOT increment  
            "Jan 13 23:51:02 testhost arpwatch: NEW STATION 11:22:33:44:55:66 eth1",  # Should increment (case insensitive)
        ]
        
        expected_increments = 2  # Only 2 entries should increment
        
        for entry in test_entries:
            exec_result = arpwatch_container.exec(
                ["sh", "-c", f'echo "{entry}" >> /var/log/arpwatch.log']
            )
            time.sleep(1)  # Small delay between entries
        
        # Wait for processing
        time.sleep(5)
        
        # Check final value
        final_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        final_value = self._extract_counter_value(final_response.text, "arpwatch_new_station_total")
        
        actual_increment = final_value - initial_value
        assert actual_increment >= expected_increments, f"Expected at least {expected_increments} increments, got {actual_increment}"
    
    def test_sample_data_injection(self, arpwatch_container):
        """Test that sample data is injected by default and increments metrics"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get metrics after container startup - should include sample data
        response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        counter_value = self._extract_counter_value(response.text, "arpwatch_new_station_total")
        
        # Should have at least 5 entries from sample data injection
        # Note: Since ARPWATCH_DEMO_DATA defaults to true, sample data should be injected
        assert counter_value >= 5, f"Expected at least 5 sample entries, got {counter_value}"
        
        # Verify the log file contains sample data
        exec_result = arpwatch_container.exec(["cat", "/var/log/arpwatch.log"])
        log_content = exec_result.output.decode('utf-8')
        
        # Check for sample data entries
        sample_indicators = [
            "arpwatch-monitor arpwatch: new station",
            "192.168.1.101",
            "d4:81:d7:23:a5:67",
            "10.0.0.50"
        ]
        
        for indicator in sample_indicators:
            assert indicator in log_content, f"Sample data indicator '{indicator}' not found in logs"
    
    def _extract_counter_value(self, metrics_text: str, counter_name: str) -> float:
        """Extract counter value from Prometheus metrics text"""
        for line in metrics_text.split('\n'):
            if line.startswith(counter_name) and not line.startswith(f"# {counter_name}"):
                # Parse line like: arpwatch_new_station_total 5.0
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return float(parts[1])
                    except ValueError:
                        pass
        return 0.0


class TestContainerHealth:
    """Test container health and basic functionality"""
    
    def test_container_builds_successfully(self):
        """Test that the Docker image builds without errors"""
        docker_client = docker.from_env()
        
        # Build image (returns tuple: image, logs)
        image, logs = docker_client.images.build(
            path=".",
            tag="arpwatch:build-test",
            dockerfile="Dockerfile",
            rm=True
        )
        
        # Verify image was created
        assert image is not None
        assert len(image.tags) > 0
        assert "arpwatch:build-test" in image.tags
        
        # Cleanup
        docker_client.images.remove(image.id, force=True)
    
    def test_container_basic_startup(self):
        """Test basic container startup without full testing"""
        # Build image first
        docker_client = docker.from_env()
        image, logs = docker_client.images.build(
            path=".",
            tag="arpwatch:startup-test", 
            dockerfile="Dockerfile",
            rm=True
        )
        
        try:
            container = DockerContainer("arpwatch:startup-test")
            container.with_env("ARPWATCH_NOTIFICATION_EMAIL_TO", "")
            
            with container:
                # Just verify it can start
                time.sleep(5)
                
                # Check if container is running
                assert container.get_container_host_ip() is not None
                
                # Basic log check
                logs = container.get_logs().decode('utf-8')
                # Should have some basic startup indicators
                assert len(logs) > 0
                
        finally:
            # Cleanup
            docker_client.images.remove(image.id, force=True)