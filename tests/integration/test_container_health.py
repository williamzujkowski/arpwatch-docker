"""
Test container startup and health checks for arpwatch-docker.
"""
import pytest
import requests
import time
from testcontainers.core.container import DockerContainer


@pytest.mark.integration
@pytest.mark.requires_docker
class TestContainerHealth:
    """Test suite for container health and startup verification."""
    
    def test_arpwatch_container_starts_successfully(self, arpwatch_container: DockerContainer):
        """Verify that arpwatch container starts and becomes healthy."""
        # Check container is running
        assert arpwatch_container.get_container_host_ip()
        
        container_info = arpwatch_container.get_wrapped_container().attrs
        container_state = container_info['State']
        
        assert container_state['Running'] is True
        assert container_state['Status'] == 'running'
        
        # Verify container didn't exit immediately
        assert container_state.get('ExitCode', 0) == 0
    
    def test_metrics_endpoint_responds(self, arpwatch_container: DockerContainer):
        """Test that metrics endpoint is accessible and returns valid data."""
        port = arpwatch_container.get_exposed_port(8000)
        metrics_url = f"http://localhost:{port}/metrics"
        
        # Test basic connectivity
        response = requests.get(metrics_url, timeout=5)
        assert response.status_code == 200
        
        # Verify content type
        assert response.headers.get('Content-Type') == 'text/plain; version=0.0.4; charset=utf-8'
        
        # Verify metrics are present
        metrics_text = response.text
        assert "arpwatch_new_station_total" in metrics_text
        assert "# HELP arpwatch_new_station_total" in metrics_text
        assert "# TYPE arpwatch_new_station_total counter" in metrics_text
    
    def test_container_healthcheck_passes(self, arpwatch_container: DockerContainer):
        """Verify that Docker healthcheck is configured and passing."""
        # Wait a bit for healthcheck to run
        time.sleep(5)
        
        container_info = arpwatch_container.get_wrapped_container().attrs
        health_status = container_info['State'].get('Health', {})
        
        # Health status should exist (healthcheck is configured)
        assert health_status, "No healthcheck configured for container"
        
        # Check health status
        assert health_status.get('Status') in ['healthy', 'starting']
        
        # If we have log entries, verify they show success
        if 'Log' in health_status:
            latest_check = health_status['Log'][-1] if health_status['Log'] else None
            if latest_check:
                assert latest_check.get('ExitCode') == 0
    
    def test_container_logs_no_errors(self, arpwatch_container: DockerContainer):
        """Check container logs for any error messages."""
        logs = arpwatch_container.get_logs().decode('utf-8')
        
        # Check for common error indicators
        error_indicators = [
            'error',
            'ERROR',
            'Error',
            'FATAL',
            'fatal',
            'Failed',
            'failed',
            'Exception',
            'Traceback'
        ]
        
        # Allow some expected log entries
        allowed_patterns = [
            'error_log',  # rsyslog configuration
            'ErrorLog',   # Apache-style config
        ]
        
        for indicator in error_indicators:
            if indicator in logs:
                # Check if it's an allowed pattern
                lines_with_indicator = [line for line in logs.split('\n') if indicator in line]
                for line in lines_with_indicator:
                    is_allowed = any(pattern in line for pattern in allowed_patterns)
                    assert is_allowed, f"Unexpected error in logs: {line}"
    
    def test_required_processes_running(self, arpwatch_container: DockerContainer, docker_client):
        """Verify that required processes are running inside the container."""
        container_id = arpwatch_container.get_wrapped_container().id
        container = docker_client.containers.get(container_id)
        
        # Check for arpwatch process
        arpwatch_check = container.exec_run("pgrep -f arpwatch", user='root')
        assert arpwatch_check.exit_code == 0, "arpwatch process not found"
        
        # Check for metrics exporter
        exporter_check = container.exec_run("pgrep -f metrics_exporter.py", user='root')
        assert exporter_check.exit_code == 0, "metrics exporter process not found"
        
        # Check for rsyslog (if used)
        rsyslog_check = container.exec_run("pgrep rsyslogd", user='root')
        # rsyslog might not be required, so we just note if it's running
        rsyslog_running = rsyslog_check.exit_code == 0
        
        # Verify at least the critical processes are running
        assert arpwatch_check.exit_code == 0 or exporter_check.exit_code == 0
    
    def test_container_restart_recovery(self, docker_client):
        """Test that container can restart and recover successfully."""
        from testcontainers.core.container import DockerContainer
        import tempfile
        
        with tempfile.TemporaryDirectory() as tmpdir:
            # Start container with restart policy
            container = DockerContainer("arpwatch:test")
            container.with_env("IFACE", "eth0")
            container.with_exposed_ports(8000)
            container.with_volume_mapping(tmpdir, "/var/log", "rw")
            
            with container:
                # Wait for initial startup
                from conftest import wait_for_http_endpoint
                wait_for_http_endpoint(container, 8000, "/metrics")
                
                # Get initial metrics
                port = container.get_exposed_port(8000)
                initial_response = requests.get(f"http://localhost:{port}/metrics")
                assert initial_response.status_code == 200
                
                # Stop the container (simulating crash)
                container_id = container.get_wrapped_container().id
                docker_container = docker_client.containers.get(container_id)
                docker_container.stop(timeout=5)
                
                # Restart the container
                docker_container.start()
                
                # Wait for recovery
                time.sleep(5)
                wait_for_http_endpoint(container, 8000, "/metrics", timeout=30)
                
                # Verify metrics endpoint is working again
                recovery_response = requests.get(f"http://localhost:{port}/metrics")
                assert recovery_response.status_code == 200
    
    @pytest.mark.slow
    def test_container_long_running_stability(self, arpwatch_container: DockerContainer):
        """Test container stability over a longer period."""
        port = arpwatch_container.get_exposed_port(8000)
        metrics_url = f"http://localhost:{port}/metrics"
        
        # Check metrics endpoint every 5 seconds for 30 seconds
        checks = []
        for i in range(6):
            try:
                response = requests.get(metrics_url, timeout=2)
                checks.append({
                    'iteration': i,
                    'status_code': response.status_code,
                    'response_time': response.elapsed.total_seconds()
                })
            except Exception as e:
                checks.append({
                    'iteration': i,
                    'error': str(e)
                })
            
            time.sleep(5)
        
        # Verify all checks passed
        failed_checks = [c for c in checks if c.get('status_code') != 200]
        assert not failed_checks, f"Health checks failed: {failed_checks}"
        
        # Verify response times are reasonable
        response_times = [c['response_time'] for c in checks if 'response_time' in c]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        assert avg_response_time < 1.0, f"Average response time too high: {avg_response_time}s"