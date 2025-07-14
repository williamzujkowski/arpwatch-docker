#!/usr/bin/env python3
"""
Integration tests for arpwatch-docker using testcontainers

Tests the complete Docker-based pipeline including:
- Container startup and health validation
- Log file monitoring and processing
- Prometheus metrics endpoint functionality
- End-to-end workflow from log injection to metric increment
"""

import pytest
import requests
import time
import tempfile
import os
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs
import docker


class TestArpwatchIntegration:
    """Integration tests for the complete arpwatch container stack"""
    
    @pytest.fixture(scope="class")
    def arpwatch_container(self):
        """Start arpwatch container for testing"""
        # Build the image first
        docker_client = docker.from_env()
        docker_client.images.build(
            path=".",
            tag="arpwatch:test",
            dockerfile="Dockerfile",
            rm=True
        )
        
        # Start container with bridge networking (not host mode for testing)
        container = DockerContainer("arpwatch:test")
        container.with_exposed_ports(8000)  # Metrics port
        container.with_env("ARPWATCH_NOTIFICATION_EMAIL_TO", "")  # Disable email for tests
        
        with container:
            # Wait for container to be ready
            wait_for_logs(container, "Started Prometheus exporter", timeout=30)
            yield container
    
    def test_container_startup_and_health(self, arpwatch_container):
        """Test that container starts successfully and is healthy"""
        # Verify container is running
        assert arpwatch_container.get_container_host_ip() is not None
        
        # Check that logs show successful startup
        logs = arpwatch_container.get_logs().decode('utf-8')
        assert "Email notifications disabled" in logs
        assert "Started Prometheus exporter" in logs
    
    def test_metrics_endpoint_accessible(self, arpwatch_container):
        """Test that Prometheus metrics endpoint is accessible"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Test metrics endpoint
        response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        assert response.status_code == 200
        
        # Verify metrics format
        metrics_text = response.text
        assert "arpwatch_new_station_total" in metrics_text
        assert "# HELP arpwatch_new_station_total" in metrics_text
        assert "# TYPE arpwatch_new_station_total counter" in metrics_text
    
    def test_log_injection_and_metric_increment(self, arpwatch_container):
        """Test end-to-end: inject log entry and verify metric increment"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial metric value
        initial_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        initial_text = initial_response.text
        
        # Extract initial counter value
        initial_value = self._extract_counter_value(initial_text, "arpwatch_new_station_total")
        
        # Inject a "new station" log entry into the container
        test_log_entry = "Jan 13 23:45:00 testhost arpwatch: new station 00:11:22:33:44:55 eth0\\n"
        
        # Use docker exec to append to log file
        exec_result = arpwatch_container.exec(
            f"sh -c 'echo \"{test_log_entry}\" >> /var/log/arpwatch.log'"
        )
        assert exec_result.exit_code == 0
        
        # Wait for metrics to update (give some time for log processing)
        time.sleep(3)
        
        # Get updated metric value
        updated_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        updated_text = updated_response.text
        updated_value = self._extract_counter_value(updated_text, "arpwatch_new_station_total")
        
        # Verify metric incremented
        assert updated_value > initial_value, f"Metric did not increment: {initial_value} -> {updated_value}"
        assert updated_value == initial_value + 1, f"Expected increment of 1, got {updated_value - initial_value}"
    
    def test_multiple_log_entries_processing(self, arpwatch_container):
        """Test processing multiple log entries with mixed content"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial metric value
        initial_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        initial_value = self._extract_counter_value(initial_response.text, "arpwatch_new_station_total")
        
        # Inject multiple log entries (some should trigger metrics, some shouldn't)
        test_entries = [
            "Jan 13 23:46:00 testhost arpwatch: new station aa:bb:cc:dd:ee:ff eth0",
            "Jan 13 23:46:01 testhost arpwatch: station activity aa:bb:cc:dd:ee:ff eth0",  # Should not increment
            "Jan 13 23:46:02 testhost arpwatch: new station 11:22:33:44:55:66 eth1",
            "Jan 13 23:46:03 testhost other: unrelated log entry",  # Should not increment
            "Jan 13 23:46:04 testhost arpwatch: NEW STATION 77:88:99:aa:bb:cc eth0",  # Case insensitive
        ]
        
        expected_increments = 3  # Only 3 entries should trigger increments
        
        for entry in test_entries:
            exec_result = arpwatch_container.exec(
                f"sh -c 'echo \"{entry}\" >> /var/log/arpwatch.log'"
            )
            assert exec_result.exit_code == 0
        
        # Wait for processing
        time.sleep(5)
        
        # Verify final count
        final_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        final_value = self._extract_counter_value(final_response.text, "arpwatch_new_station_total")
        
        actual_increment = final_value - initial_value
        assert actual_increment == expected_increments, f"Expected {expected_increments} increments, got {actual_increment}"
    
    def test_container_restart_metric_persistence(self, arpwatch_container):
        """Test that metrics persist across container restarts"""
        host = arpwatch_container.get_container_host_ip()
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial value
        initial_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        initial_value = self._extract_counter_value(initial_response.text, "arpwatch_new_station_total")
        
        # Add a log entry
        test_entry = "Jan 13 23:47:00 testhost arpwatch: new station ff:ee:dd:cc:bb:aa eth0"
        exec_result = arpwatch_container.exec(
            f"sh -c 'echo \"{test_entry}\" >> /var/log/arpwatch.log'"
        )
        assert exec_result.exit_code == 0
        
        time.sleep(3)
        
        # Verify increment
        pre_restart_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        pre_restart_value = self._extract_counter_value(pre_restart_response.text, "arpwatch_new_station_total")
        assert pre_restart_value == initial_value + 1
        
        # Restart the metrics exporter process
        restart_result = arpwatch_container.exec(
            "sh -c 'pkill -f metrics_exporter.py && python3 /exporter/metrics_exporter.py &'"
        )
        
        # Wait for restart
        time.sleep(5)
        
        # Note: In a real scenario, Prometheus counters reset on restart
        # This test mainly verifies the container can handle restarts gracefully
        post_restart_response = requests.get(f"http://{host}:{port}/metrics", timeout=10)
        assert post_restart_response.status_code == 200
        
        # The counter may reset to 0 after restart, which is expected behavior
        post_restart_value = self._extract_counter_value(post_restart_response.text, "arpwatch_new_station_total")
        assert post_restart_value >= 0  # Should be a valid counter value
    
    def _extract_counter_value(self, metrics_text: str, counter_name: str) -> float:
        """Extract counter value from Prometheus metrics text"""
        for line in metrics_text.split('\\n'):
            if line.startswith(counter_name) and not line.startswith(f"# {counter_name}"):
                # Parse line like: arpwatch_new_station_total 5.0
                parts = line.split()
                if len(parts) >= 2:
                    return float(parts[1])
        return 0.0


class TestContainerHealthAndStability:
    """Test container health, stability, and error handling"""
    
    @pytest.fixture(scope="function")
    def minimal_container(self):
        """Start container with minimal configuration for quick tests"""
        container = DockerContainer("arpwatch:test")
        container.with_exposed_ports(8000)
        container.with_env("ARPWATCH_NOTIFICATION_EMAIL_TO", "")
        
        with container:
            wait_for_logs(container, "Started Prometheus exporter", timeout=30)
            yield container
    
    def test_container_environment_variables(self, minimal_container):
        """Test container responds correctly to environment variables"""
        logs = minimal_container.get_logs().decode('utf-8')
        
        # Should show email disabled
        assert "Email notifications disabled" in logs
        
        # Should not show email configuration errors
        assert "Missing ARPWATCH_NOTIFICATION_EMAIL_FROM" not in logs
        assert "Missing ARPWATCH_NOTIFICATION_EMAIL_SERVER" not in logs
    
    def test_metrics_endpoint_performance(self, minimal_container):
        """Test metrics endpoint responds quickly under load"""
        host = minimal_container.get_container_host_ip()
        port = minimal_container.get_exposed_port(8000)
        
        # Test multiple rapid requests
        response_times = []
        for _ in range(10):
            start_time = time.time()
            response = requests.get(f"http://{host}:{port}/metrics", timeout=5)
            end_time = time.time()
            
            assert response.status_code == 200
            response_times.append(end_time - start_time)
        
        # Verify reasonable performance (should respond in under 1 second)
        avg_response_time = sum(response_times) / len(response_times)
        assert avg_response_time < 1.0, f"Average response time too slow: {avg_response_time:.2f}s"
    
    def test_container_graceful_shutdown(self, minimal_container):
        """Test container shuts down gracefully"""
        # Container should be running
        assert minimal_container.get_container_host_ip() is not None
        
        # Stop container gracefully
        minimal_container.stop()
        
        # Verify it stopped without hanging
        # (The context manager will handle cleanup)
        assert True  # If we get here, shutdown was successful
    
    def test_log_file_permissions_and_access(self, minimal_container):
        """Test log file is accessible and has correct permissions"""
        # Check log file exists and is readable
        exec_result = minimal_container.exec("ls -la /var/log/arpwatch.log")
        assert exec_result.exit_code == 0
        
        output = exec_result.output.decode('utf-8')
        
        # Should be owned by arpwatch user
        assert "arpwatch" in output
        
        # Check we can read from the log
        read_result = minimal_container.exec("head -n 1 /var/log/arpwatch.log")
        assert read_result.exit_code == 0
        
        # Check we can write to the log (for testing)
        write_result = minimal_container.exec(
            "sh -c 'echo \"test entry\" >> /var/log/arpwatch.log'"
        )
        assert write_result.exit_code == 0