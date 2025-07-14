"""
Test log file monitoring and metrics generation for arpwatch-docker.
"""
import pytest
import requests
import time
from datetime import datetime
from testcontainers.core.container import DockerContainer


@pytest.mark.integration
@pytest.mark.requires_docker
class TestLogMonitoring:
    """Test suite for log monitoring and metrics generation."""
    
    def test_log_injection_triggers_metrics(
        self,
        arpwatch_container: DockerContainer,
        inject_log_entry,
        wait_for_metric_update
    ):
        """Test that injecting log entries updates metrics correctly."""
        # Get initial metric value
        port = arpwatch_container.get_exposed_port(8000)
        response = requests.get(f"http://localhost:{port}/metrics")
        assert response.status_code == 200
        
        from conftest import parse_prometheus_metric
        initial_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Inject a new station log entry
        timestamp = datetime.now().strftime("%b %d %H:%M:%S")
        log_entry = f"{timestamp} arpwatch: new station 192.168.1.100 aa:bb:cc:dd:ee:ff eth0"
        inject_log_entry(arpwatch_container, log_entry)
        
        # Wait for metric to update
        assert wait_for_metric_update(
            arpwatch_container,
            "arpwatch_new_station_total",
            expected_delta=1
        ), "Metric did not update after log injection"
        
        # Verify final metric value
        response = requests.get(f"http://localhost:{port}/metrics")
        final_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        assert final_count == initial_count + 1
    
    def test_multiple_log_entries(
        self,
        arpwatch_container: DockerContainer,
        inject_log_entry,
        docker_client
    ):
        """Test handling of multiple rapid log entries."""
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial count
        response = requests.get(f"http://localhost:{port}/metrics")
        from conftest import parse_prometheus_metric
        initial_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Inject multiple log entries
        test_entries = [
            "new station 192.168.1.101 aa:bb:cc:dd:ee:01 eth0",
            "new station 192.168.1.102 aa:bb:cc:dd:ee:02 eth0",
            "new station 192.168.1.103 aa:bb:cc:dd:ee:03 eth0",
            "changed ethernet address 192.168.1.104",  # Different type
            "new station 192.168.1.105 aa:bb:cc:dd:ee:05 eth0",
        ]
        
        new_station_count = sum(1 for entry in test_entries if "new station" in entry)
        
        for entry in test_entries:
            timestamp = datetime.now().strftime("%b %d %H:%M:%S")
            log_entry = f"{timestamp} arpwatch: {entry}"
            inject_log_entry(arpwatch_container, log_entry)
            time.sleep(0.1)  # Small delay between entries
        
        # Wait for metrics to update
        time.sleep(2)
        
        # Verify count increased correctly
        response = requests.get(f"http://localhost:{port}/metrics")
        final_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        assert final_count == initial_count + new_station_count
    
    def test_log_pattern_matching(
        self,
        arpwatch_container: DockerContainer,
        inject_log_entry
    ):
        """Test that only matching log patterns trigger metric updates."""
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial count
        response = requests.get(f"http://localhost:{port}/metrics")
        from conftest import parse_prometheus_metric
        initial_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Inject various log entries
        test_cases = [
            ("new station 192.168.1.200 ff:ff:ff:ff:ff:ff eth0", True),
            ("NEW STATION 192.168.1.201 ff:ff:ff:ff:ff:01 eth0", True),  # Case insensitive
            ("changed ethernet address 192.168.1.202", False),
            ("flip flop 192.168.1.203", False),
            ("bogon 192.168.1.204", False),
            ("NeW sTaTiOn 192.168.1.205 ff:ff:ff:ff:ff:05 eth0", True),  # Mixed case
        ]
        
        expected_increment = sum(1 for _, should_match in test_cases if should_match)
        
        for log_content, _ in test_cases:
            timestamp = datetime.now().strftime("%b %d %H:%M:%S")
            log_entry = f"{timestamp} arpwatch: {log_content}"
            inject_log_entry(arpwatch_container, log_entry)
            time.sleep(0.2)
        
        # Wait for processing
        time.sleep(2)
        
        # Verify only matching entries incremented the counter
        response = requests.get(f"http://localhost:{port}/metrics")
        final_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        assert final_count == initial_count + expected_increment
    
    def test_log_file_rotation_handling(
        self,
        arpwatch_container: DockerContainer,
        docker_client,
        inject_log_entry
    ):
        """Test that metrics continue working after log rotation."""
        port = arpwatch_container.get_exposed_port(8000)
        container_id = arpwatch_container.get_wrapped_container().id
        container = docker_client.containers.get(container_id)
        
        # Get initial metric
        response = requests.get(f"http://localhost:{port}/metrics")
        from conftest import parse_prometheus_metric
        initial_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Inject a log entry
        inject_log_entry(arpwatch_container, f"{datetime.now():%b %d %H:%M:%S} arpwatch: new station 192.168.1.50 aa:aa:aa:aa:aa:aa eth0")
        time.sleep(1)
        
        # Simulate log rotation
        rotation_commands = [
            "mv /var/log/arpwatch.log /var/log/arpwatch.log.1",
            "touch /var/log/arpwatch.log",
            "chown arpwatch:arpwatch /var/log/arpwatch.log",
        ]
        
        for cmd in rotation_commands:
            result = container.exec_run(f"/bin/sh -c '{cmd}'", user='root')
            assert result.exit_code == 0, f"Command failed: {cmd}"
        
        # Wait a moment for the exporter to handle rotation
        time.sleep(2)
        
        # Inject another log entry to the new file
        inject_log_entry(arpwatch_container, f"{datetime.now():%b %d %H:%M:%S} arpwatch: new station 192.168.1.51 bb:bb:bb:bb:bb:bb eth0")
        time.sleep(1)
        
        # Verify metrics still update
        response = requests.get(f"http://localhost:{port}/metrics")
        final_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Should have increased by 2 (one before rotation, one after)
        assert final_count >= initial_count + 2
    
    def test_concurrent_log_writes(
        self,
        arpwatch_container: DockerContainer,
        docker_client
    ):
        """Test handling of concurrent log writes."""
        import concurrent.futures
        from threading import Lock
        
        port = arpwatch_container.get_exposed_port(8000)
        container_id = arpwatch_container.get_wrapped_container().id
        container = docker_client.containers.get(container_id)
        
        # Get initial count
        response = requests.get(f"http://localhost:{port}/metrics")
        from conftest import parse_prometheus_metric
        initial_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Function to inject log entry
        write_lock = Lock()
        
        def write_log_entry(index: int):
            timestamp = datetime.now().strftime("%b %d %H:%M:%S")
            log_entry = f"{timestamp} arpwatch: new station 192.168.2.{index} aa:bb:cc:dd:ee:{index:02x} eth0"
            
            with write_lock:  # Ensure atomic writes
                result = container.exec_run(
                    f"/bin/sh -c 'echo \"{log_entry}\" >> /var/log/arpwatch.log'",
                    user='root'
                )
                return result.exit_code == 0
        
        # Write 20 entries concurrently
        num_entries = 20
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(write_log_entry, i) for i in range(num_entries)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # Verify all writes succeeded
        assert all(results), "Some log writes failed"
        
        # Wait for metrics to update
        time.sleep(3)
        
        # Verify all entries were counted
        response = requests.get(f"http://localhost:{port}/metrics")
        final_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        assert final_count == initial_count + num_entries
    
    def test_malformed_log_entries(
        self,
        arpwatch_container: DockerContainer,
        inject_log_entry
    ):
        """Test that malformed log entries don't crash the exporter."""
        port = arpwatch_container.get_exposed_port(8000)
        
        # Get initial count
        response = requests.get(f"http://localhost:{port}/metrics")
        from conftest import parse_prometheus_metric
        initial_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        
        # Inject various malformed entries
        malformed_entries = [
            "",  # Empty line
            "malformed entry without timestamp",
            f"{datetime.now():%b %d %H:%M:%S}",  # Timestamp only
            "new station",  # Partial match
            "\x00\x01\x02\x03",  # Binary data
            "🚀 emoji new station test",  # Unicode
            "a" * 1000,  # Very long line
        ]
        
        for entry in malformed_entries:
            inject_log_entry(arpwatch_container, entry)
            time.sleep(0.1)
        
        # Inject one valid entry
        valid_entry = f"{datetime.now():%b %d %H:%M:%S} arpwatch: new station 192.168.1.99 ff:ff:ff:ff:ff:ff eth0"
        inject_log_entry(arpwatch_container, valid_entry)
        
        # Wait for processing
        time.sleep(2)
        
        # Verify exporter is still working and counted only the valid entry
        response = requests.get(f"http://localhost:{port}/metrics")
        assert response.status_code == 200
        
        final_count = parse_prometheus_metric(response.text, "arpwatch_new_station_total")
        assert final_count == initial_count + 1  # Only the valid entry should count