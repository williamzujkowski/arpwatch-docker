"""
Test Prometheus integration with arpwatch-docker.
"""
import pytest
import requests
import time
import json
from urllib.parse import quote
from testcontainers.compose import DockerCompose


@pytest.mark.integration
@pytest.mark.requires_docker
class TestPrometheusIntegration:
    """Test suite for Prometheus integration and metrics scraping."""
    
    def get_prometheus_port(self, compose: DockerCompose) -> int:
        """Helper to get Prometheus exposed port."""
        # This is a simplified version - actual implementation would need
        # to query docker-compose for the mapped port
        return compose.get_service_port("prometheus", 9090)
    
    def get_arpwatch_port(self, compose: DockerCompose) -> int:
        """Helper to get arpwatch metrics port."""
        return compose.get_service_port("arpwatch", 8000)
    
    @pytest.mark.slow
    def test_prometheus_scrapes_arpwatch_metrics(self, docker_compose_services: DockerCompose):
        """Test that Prometheus successfully scrapes arpwatch metrics."""
        # Wait for Prometheus to perform initial scrape
        time.sleep(15)
        
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Query Prometheus for arpwatch metrics
        query = quote("arpwatch_new_station_total")
        prometheus_url = f"http://localhost:{prometheus_port}/api/v1/query?query={query}"
        
        response = requests.get(prometheus_url, timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        
        # Check if we have results
        results = data['data']['result']
        assert isinstance(results, list)
        
        if results:  # Metric exists
            result = results[0]
            assert result['metric']['__name__'] == 'arpwatch_new_station_total'
            assert 'value' in result
            assert len(result['value']) == 2  # [timestamp, value]
            
            # Verify it's a valid number
            metric_value = float(result['value'][1])
            assert metric_value >= 0
    
    def test_prometheus_targets_health(self, docker_compose_services: DockerCompose):
        """Test that Prometheus targets are healthy."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Wait for targets to be discovered
        time.sleep(10)
        
        # Check targets endpoint
        response = requests.get(
            f"http://localhost:{prometheus_port}/api/v1/targets",
            timeout=10
        )
        assert response.status_code == 200
        
        targets_data = response.json()
        assert targets_data['status'] == 'success'
        
        active_targets = targets_data['data']['activeTargets']
        assert len(active_targets) > 0
        
        # Find arpwatch target
        arpwatch_targets = [
            t for t in active_targets 
            if 'arpwatch' in t.get('labels', {}).get('job', '')
        ]
        
        assert len(arpwatch_targets) > 0, "No arpwatch target found in Prometheus"
        
        # Check arpwatch target health
        arpwatch_target = arpwatch_targets[0]
        assert arpwatch_target['health'] == 'up', f"Arpwatch target is not healthy: {arpwatch_target}"
        
        # Verify last scrape was successful
        assert arpwatch_target.get('lastScrape'), "No last scrape time recorded"
        assert arpwatch_target.get('lastScrapeDuration'), "No scrape duration recorded"
    
    def test_prometheus_scrape_interval(self, docker_compose_services: DockerCompose):
        """Test that Prometheus scrapes at the configured interval."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Query for up metric to check scrape timestamps
        query = quote('up{job="arpwatch"}')
        
        # Collect samples over time
        samples = []
        for _ in range(3):
            response = requests.get(
                f"http://localhost:{prometheus_port}/api/v1/query?query={query}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['data']['result']:
                    timestamp = data['data']['result'][0]['value'][0]
                    samples.append(timestamp)
            
            time.sleep(6)  # Wait longer than scrape interval
        
        # Verify we got multiple samples
        assert len(samples) >= 2, "Not enough samples collected"
        
        # Check intervals between samples (should be ~5s based on config)
        intervals = [samples[i+1] - samples[i] for i in range(len(samples)-1)]
        
        for interval in intervals:
            # Allow some variance (4-6 seconds)
            assert 4 <= interval <= 6, f"Scrape interval {interval}s outside expected range"
    
    def test_prometheus_metric_persistence(self, docker_compose_services: DockerCompose):
        """Test that metrics persist across scrapes."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        arpwatch_port = self.get_arpwatch_port(docker_compose_services)
        
        # Inject a log entry to increment counter
        # Note: This would require access to the container, simplified here
        
        # Query metric over time
        query = quote("arpwatch_new_station_total")
        values = []
        
        for _ in range(3):
            response = requests.get(
                f"http://localhost:{prometheus_port}/api/v1/query?query={query}",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data['data']['result']:
                    value = float(data['data']['result'][0]['value'][1])
                    values.append(value)
            
            time.sleep(5)
        
        # Counter metrics should never decrease
        for i in range(1, len(values)):
            assert values[i] >= values[i-1], f"Counter decreased: {values}"
    
    def test_prometheus_query_range(self, docker_compose_services: DockerCompose):
        """Test Prometheus range queries for historical data."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Wait for some data to accumulate
        time.sleep(20)
        
        # Query last 1 minute of data
        end_time = int(time.time())
        start_time = end_time - 60
        
        query = quote("arpwatch_new_station_total")
        range_url = (
            f"http://localhost:{prometheus_port}/api/v1/query_range"
            f"?query={query}"
            f"&start={start_time}"
            f"&end={end_time}"
            f"&step=5"
        )
        
        response = requests.get(range_url, timeout=10)
        assert response.status_code == 200
        
        data = response.json()
        assert data['status'] == 'success'
        
        if data['data']['result']:
            result = data['data']['result'][0]
            values = result['values']
            
            # Should have multiple data points
            assert len(values) > 1, "Not enough data points in range query"
            
            # Verify data structure
            for value in values:
                assert len(value) == 2  # [timestamp, value]
                assert isinstance(value[0], (int, float))  # timestamp
                assert isinstance(value[1], str)  # value as string
    
    def test_prometheus_alerting_rules(self, docker_compose_services: DockerCompose):
        """Test that Prometheus can evaluate alerting rules."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Check rules endpoint
        response = requests.get(
            f"http://localhost:{prometheus_port}/api/v1/rules",
            timeout=10
        )
        assert response.status_code == 200
        
        rules_data = response.json()
        assert rules_data['status'] == 'success'
        
        # Note: This would show configured rules if any were defined
        # in the Prometheus configuration
    
    def test_prometheus_metadata(self, docker_compose_services: DockerCompose):
        """Test Prometheus metadata endpoints."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Test metadata endpoint
        response = requests.get(
            f"http://localhost:{prometheus_port}/api/v1/metadata",
            timeout=10
        )
        assert response.status_code == 200
        
        metadata = response.json()
        assert metadata['status'] == 'success'
        
        # Check for arpwatch metrics metadata
        arpwatch_metrics = metadata['data'].get('arpwatch_new_station_total')
        if arpwatch_metrics:
            assert len(arpwatch_metrics) > 0
            metric_info = arpwatch_metrics[0]
            assert metric_info.get('type') == 'counter'
            assert 'help' in metric_info
    
    def test_prometheus_service_discovery(self, docker_compose_services: DockerCompose):
        """Test Prometheus service discovery configuration."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        
        # Check service discovery endpoint
        response = requests.get(
            f"http://localhost:{prometheus_port}/api/v1/targets/metadata",
            timeout=10
        )
        assert response.status_code == 200
        
        sd_data = response.json()
        assert sd_data['status'] == 'success'
        
        # Look for arpwatch target metadata
        for target in sd_data['data']:
            if 'arpwatch' in target.get('labels', {}).get('job', ''):
                # Verify expected labels
                assert 'instance' in target['labels']
                assert '__address__' in target['discoveredLabels']
                break
    
    @pytest.mark.slow
    def test_metrics_availability_over_time(self, docker_compose_services: DockerCompose):
        """Test that metrics remain available over extended period."""
        prometheus_port = self.get_prometheus_port(docker_compose_services)
        arpwatch_port = self.get_arpwatch_port(docker_compose_services)
        
        # Monitor for 30 seconds with checks every 5 seconds
        availability_checks = []
        
        for i in range(6):
            # Check arpwatch metrics directly
            try:
                arpwatch_response = requests.get(
                    f"http://localhost:{arpwatch_port}/metrics",
                    timeout=2
                )
                arpwatch_available = arpwatch_response.status_code == 200
            except:
                arpwatch_available = False
            
            # Check Prometheus query
            try:
                query = quote("up{job='arpwatch'}")
                prom_response = requests.get(
                    f"http://localhost:{prometheus_port}/api/v1/query?query={query}",
                    timeout=2
                )
                prom_available = prom_response.status_code == 200
            except:
                prom_available = False
            
            availability_checks.append({
                'iteration': i,
                'arpwatch': arpwatch_available,
                'prometheus': prom_available,
                'timestamp': time.time()
            })
            
            time.sleep(5)
        
        # Verify high availability
        arpwatch_uptime = sum(1 for c in availability_checks if c['arpwatch']) / len(availability_checks)
        prometheus_uptime = sum(1 for c in availability_checks if c['prometheus']) / len(availability_checks)
        
        assert arpwatch_uptime >= 0.8, f"Arpwatch availability too low: {arpwatch_uptime*100}%"
        assert prometheus_uptime >= 0.8, f"Prometheus availability too low: {prometheus_uptime*100}%"