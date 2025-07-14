# arpwatch-docker

A comprehensive **enterprise-grade network monitoring solution** that combines arpwatch with modern observability tools. This container builds arpwatch from source, provides Prometheus metrics for all arpwatch event types, includes a professional Grafana dashboard, and features automatic process health monitoring with self-healing capabilities.

## 🚀 Key Features

- **📊 Complete Monitoring Stack**: Arpwatch → Prometheus → Grafana pipeline
- **🔐 Security Event Detection**: Monitors for ARP spoofing, network intrusions, and configuration issues  
- **📈 Professional Dashboard**: Auto-provisioned Grafana dashboard with real-time visualizations
- **🔄 Self-Healing**: Automatic arpwatch process restart with exponential backoff
- **📧 Email Alerts**: Optional email notifications for network events
- **⚡ Immediate Visibility**: Sample data injection for instant setup validation
- **🏥 Health Monitoring**: Comprehensive health checks and process monitoring
- **📦 Zero-Config Setup**: Auto-provisioning for all monitoring components

## 🔥 Quick Start

1. **Clone and configure**:
   ```bash
   git clone https://github.com/williamzujkowski/arpwatch-docker.git
   cd arpwatch-docker
   cp .env.example .env
   # Edit .env as needed (defaults work for immediate testing)
   ```

2. **Launch the complete monitoring stack**:
   ```bash
   docker-compose up -d --build
   ```

3. **Access your monitoring dashboards**:
   - **Grafana Dashboard**: http://localhost:3000 (admin/admin)
   - **Prometheus Metrics**: http://localhost:9090
   - **Raw Metrics**: http://localhost:8000/metrics

4. **Immediate validation**: See sample data in all dashboards within 30 seconds!

## 📊 Monitoring Capabilities

### Network Security Events Tracked
| Event Type | Metric | Security Significance |
|------------|--------|----------------------|
| **Flip Flop** | `arpwatch_flip_flop_total` | 🚨 **Critical**: Potential ARP spoofing/MITM attack |
| **Bogon Events** | `arpwatch_bogon_total` | ⚠️ **High**: Invalid network activity, possible intrusion |
| **Ethernet Mismatch** | `arpwatch_ethernet_mismatch_total` | ⚠️ **Medium**: Packet inconsistencies, configuration issues |
| **New Stations** | `arpwatch_new_station_total` | ℹ️ **Info**: New devices joining network |
| **MAC Changes** | `arpwatch_changed_ethernet_total` | ⚠️ **Medium**: Device MAC address changes |
| **Reused MACs** | `arpwatch_reused_ethernet_total` | ℹ️ **Info**: MAC address reuse patterns |
| **New Activity** | `arpwatch_new_activity_total` | ℹ️ **Info**: Devices active after 6+ months |
| **Broadcast Events** | `arpwatch_*_broadcast_total` | ℹ️ **Info**: Network broadcast activity |

### System Health Metrics
| Metric | Description |
|--------|-------------|
| `arpwatch_process_health` | Process status (1=running, 0=stopped) |
| `arpwatch_restart_count_total` | Automatic restart counter |
| `arpwatch_last_activity_timestamp` | Last log activity timestamp |
| `arpwatch_total_events_total` | Total events processed |

## 🎛️ Configuration Options

### Environment Variables (.env file)
```bash
# Sample data for immediate testing (recommended: true)
ARPWATCH_DEMO_DATA=true

# Email notifications (optional)
ARPWATCH_NOTIFICATION_EMAIL_TO=alerts@example.com
ARPWATCH_NOTIFICATION_EMAIL_FROM=arpwatch@example.com  
ARPWATCH_NOTIFICATION_EMAIL_SERVER=smtp.example.com

# Network interface (optional - auto-detected)
ARPWATCH_INTERFACE=eth0

# Grafana access (automatic)
# Dashboard: http://localhost:3000 (admin/admin)
```

### Docker Compose Customization
- **Resource Limits**: Add memory/CPU limits to service definitions
- **Port Changes**: Modify port mappings in docker-compose.yml
- **Grafana Disable**: Comment out Grafana service if not needed
- **Network Mode**: Currently uses host networking for arpwatch access

## 🏥 Health Monitoring & Reliability

### Automatic Process Monitoring
- ✅ **30-second health checks** of arpwatch process
- ✅ **Automatic restart** with exponential backoff (up to 5 attempts)
- ✅ **Restart counting** and metrics tracking
- ✅ **Graceful degradation** when max restarts reached
- ✅ **Container stability** maintained even during arpwatch failures

### Health Check Endpoint
The container provides comprehensive health checking:
```bash
# Manual health check
docker exec <container> /health-check.sh

# Health status via Docker
docker ps  # Shows (healthy) status
```

## 📈 Grafana Dashboard

### Professional Security Monitoring
The auto-provisioned dashboard provides:

- **🚨 Security Alert Panels**: Critical events prominently displayed
- **📊 Activity Timeline**: Network activity patterns over time  
- **⚡ Real-time Metrics**: Live updating counters and gauges
- **🎨 Color-coded Alerts**: Red (critical), Yellow (warning), Green (normal)
- **📱 Responsive Design**: Works on desktop, tablet, and mobile
- **⚙️ System Health**: Process monitoring and restart tracking

### Dashboard Access
- **URL**: http://localhost:3000
- **Credentials**: admin / admin (change in production!)
- **Dashboard**: "Arpwatch Network Monitoring" (auto-loaded)

## 🔧 Troubleshooting

### Common Issues

**Arpwatch not detecting events:**
```bash
# Check if arpwatch is running
docker exec <container> ps aux | grep arpwatch

# Verify network interface
docker exec <container> ip link show

# Check arpwatch logs
docker logs <container> | grep arpwatch
```

**Metrics not updating:**
```bash
# Check metrics endpoint
curl http://localhost:8000/metrics | grep arpwatch

# Verify Prometheus scraping
curl http://localhost:9090/api/v1/targets
```

**Grafana dashboard not loading:**
```bash
# Check Grafana health
curl http://localhost:3000/api/health

# Verify dashboard provisioning
docker logs <grafana-container> | grep provision
```

### Advanced Configuration

**Custom Network Interface:**
```bash
# In .env file
ARPWATCH_INTERFACE=eth1

# Or in docker-compose.yml
environment:
  - ARPWATCH_INTERFACE=bond0
```

**Production Email Setup:**
```bash
# Configure in .env
ARPWATCH_NOTIFICATION_EMAIL_TO=security-team@company.com
ARPWATCH_NOTIFICATION_EMAIL_FROM=arpwatch@monitoring.company.com
ARPWATCH_NOTIFICATION_EMAIL_SERVER=smtp.company.com
```

## 🏗️ Architecture

### Component Stack
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│    Arpwatch     │───▶│   Prometheus    │───▶│    Grafana      │
│  (Monitoring)   │    │   (Metrics)     │    │ (Visualization) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       ▲                       ▲
         ▼                       │                       │
┌─────────────────┐    ┌─────────────────┐              │
│ Metrics Exporter│────┘                 │              │
│ (Log Processing)│                      │              │
└─────────────────┘                      │              │
         │                               │              │
         ▼                               │              │
┌─────────────────┐                      │              │
│ Health Monitor  │──────────────────────┘              │
│ (Auto-restart)  │                                     │
└─────────────────┘                                     │
                                                        │
┌─────────────────────────────────────────────────────────┘
│ Auto-provisioning (Dashboards + Datasources)
└─────────────────────────────────────────────────────────┘
```

### File Structure
```
arpwatch-docker/
├── docker-compose.yml          # Complete monitoring stack
├── Dockerfile                  # Arpwatch + dependencies
├── cmd.sh                      # Entrypoint with monitoring
├── exporter/
│   └── metrics_exporter.py     # Prometheus metrics exporter
├── scripts/
│   └── health-check.sh         # Enhanced health checking
├── prometheus/
│   └── prometheus.yml          # Prometheus configuration
├── grafana/
│   └── provisioning/
│       ├── datasources/        # Auto-provisioned Prometheus
│       └── dashboards/         # Auto-provisioned dashboard
└── .env.example                # Configuration template
```

## 🛡️ Security Considerations

- **Capabilities**: Uses Linux capabilities instead of root privileges
- **Network Access**: Minimal required permissions for arpwatch
- **Default Credentials**: Change Grafana admin password in production
- **Email Security**: Use authenticated SMTP in production environments
- **Log Retention**: Configure appropriate log rotation policies

## 🚀 Production Deployment

### Resource Requirements
- **Memory**: ~200MB (arpwatch: 50MB, Prometheus: 100MB, Grafana: 150MB)
- **CPU**: Low (network monitoring is not CPU intensive)
- **Storage**: ~100MB for container images + metric retention
- **Network**: Host network access required for arpwatch monitoring

### Production Checklist
- [ ] Change default Grafana password
- [ ] Configure email authentication  
- [ ] Set up log rotation
- [ ] Configure backup for Grafana dashboards
- [ ] Set appropriate resource limits
- [ ] Configure alerting rules in Prometheus
- [ ] Test disaster recovery procedures

---

## 🏆 Features Summary

This solution provides **enterprise-grade network monitoring** with:
- ✅ **Complete observability stack** with zero manual configuration
- ✅ **Security-focused monitoring** for threat detection
- ✅ **Professional visualization** with Grafana dashboards  
- ✅ **Automatic healing** and reliability features
- ✅ **Production-ready** architecture and practices
- ✅ **Immediate validation** with sample data
- ✅ **Comprehensive documentation** and troubleshooting

Perfect for **security teams**, **network administrators**, and **DevOps engineers** who need reliable network monitoring with modern observability tools.

