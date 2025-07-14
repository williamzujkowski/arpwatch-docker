# syntax=docker/dockerfile:1

### === Build Stage ===
FROM ubuntu:24.04 AS builder
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 wget ca-certificates \
      build-essential autoconf automake libpcap-dev libwrap0-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /tmp
RUN wget --no-verbose https://ee.lbl.gov/downloads/arpwatch/arpwatch-2.1a15.tar.gz \
      -O arpwatch.tar.gz \
    && tar -xzf arpwatch.tar.gz

WORKDIR /tmp/arpwatch-2.1a15
RUN ./configure --prefix=/usr/local \
    && make \
    && make install

# Ethercodes build (local CSV avoids HTTP 418)
RUN wget --progress=dot:giga -O oui.csv https://standards-oui.ieee.org/oui/oui.csv \
 && wget --progress=dot:giga -O /usr/local/bin/fetch_ethercodes.py \
      https://raw.githubusercontent.com/frispete/fetch-ethercodes/master/fetch_ethercodes.py \
 && chmod +x /usr/local/bin/fetch_ethercodes.py \
 && fetch_ethercodes.py -k -o /ethercodes.dat

### === Runtime Stage ===
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      nullmailer rsyslog psmisc python3 wget sudo \
      python3-prometheus-client python3-watchdog python3-psutil \
      libpcap0.8 libwrap0 iproute2 \
    && rm -rf /var/lib/apt/lists/*

# 1) Create the arpwatch user before any chown
RUN useradd --no-create-home --shell /usr/sbin/nologin arpwatch

# 2) Prepare filesystem and set ownership
RUN mkdir -p /var/log /var/lib/arpwatch /usr/local/arpwatch \
  && touch /var/log/arpwatch.log /var/lib/arpwatch/arp.dat \
  && chown -R arpwatch:arpwatch /var/log/arpwatch.log \
  && chown -R arpwatch:arpwatch /var/lib/arpwatch \
  && chown -R arpwatch:arpwatch /usr/local/arpwatch \
  && chmod 755 /var/lib/arpwatch /usr/local/arpwatch \
  && chmod 644 /var/lib/arpwatch/arp.dat

# 3) Copy built artifacts
COPY --from=builder /usr/local/sbin/arpwatch  /usr/local/sbin/arpwatch
COPY --from=builder /ethercodes.dat          /usr/share/arpwatch/ethercodes.dat

# 4) Application scripts
COPY cmd.sh       /cmd.sh
COPY rsyslog.conf /rsyslog.conf
COPY exporter/metrics_exporter.py /exporter/metrics_exporter.py
COPY scripts/health-check.sh /health-check.sh
RUN chmod +x /exporter/metrics_exporter.py /health-check.sh

# Add capabilities for network access or install setcap
RUN apt-get update && apt-get install -y --no-install-recommends libcap2-bin \
    && rm -rf /var/lib/apt/lists/* \
    && setcap cap_net_raw,cap_net_admin+eip /usr/local/sbin/arpwatch

# Don't switch to arpwatch user yet - we need to start as root to access capabilities
# The cmd.sh script will handle dropping privileges appropriately
ENTRYPOINT ["bash", "/cmd.sh"]
