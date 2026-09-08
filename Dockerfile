# ─────────────────────────────────────────────────────────────────────────────
# Teleblock — Asterisk 20 LTS (arm64 / Raspberry Pi 5)
# Builds Asterisk from source on debian:bookworm-slim.
# Uses network_mode: host so SIP/RTP reach the HT813 on the real LAN.
# ─────────────────────────────────────────────────────────────────────────────
FROM debian:bookworm-slim AS builder

ENV ASTERISK_VERSION=20
ENV DEBIAN_FRONTEND=noninteractive

# Build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    wget \
    ca-certificates \
    libssl-dev \
    libncurses5-dev \
    libedit-dev \
    uuid-dev \
    libjansson-dev \
    libxml2-dev \
    libsqlite3-dev \
    libsrtp2-dev \
    libnewt-dev \
    libreadline-dev \
    pkg-config \
    unzip \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src

# Download and extract Asterisk 20 LTS
RUN wget -q "https://downloads.asterisk.org/pub/telephony/asterisk/asterisk-${ASTERISK_VERSION}-current.tar.gz" \
    && tar xzf "asterisk-${ASTERISK_VERSION}-current.tar.gz" \
    && rm "asterisk-${ASTERISK_VERSION}-current.tar.gz"

# Build and install
RUN cd asterisk-${ASTERISK_VERSION}.*/ \
    && ./configure \
        --with-jansson-bundled \
        --with-pjproject-bundled \
    && make -j$(nproc) \
    && make install \
    && make samples \
    && make config

# ─── Runtime stage ────────────────────────────────────────────────────────────
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl3 \
    libncurses6 \
    libedit2 \
    uuid-runtime \
    libxml2 \
    libsqlite3-0 \
    libsrtp2-1 \
    libnewt0.52 \
    libreadline8 \
    && rm -rf /var/lib/apt/lists/*

# Copy Asterisk installation from builder
COPY --from=builder /usr/sbin/asterisk /usr/sbin/asterisk
COPY --from=builder /usr/lib/asterisk /usr/lib/asterisk
COPY --from=builder /usr/lib/libasteriskssl.so* /usr/lib/
COPY --from=builder /usr/lib/libasteriskpj.so* /usr/lib/
COPY --from=builder /var/lib/asterisk /var/lib/asterisk
COPY --from=builder /var/spool/asterisk /var/spool/asterisk
COPY --from=builder /etc/asterisk /etc/asterisk
COPY --from=builder /usr/include/asterisk* /usr/include/

RUN ldconfig

# Create asterisk user
RUN groupadd -r asterisk && useradd -r -g asterisk asterisk

# Runtime directories
RUN mkdir -p \
    /var/lib/asterisk/sounds/teleblock \
    /var/log/asterisk \
    /var/run/asterisk \
    /var/lib/teleblock \
    /var/log/teleblock \
    && chown -R asterisk:asterisk \
        /var/lib/asterisk \
        /var/log/asterisk \
        /var/run/asterisk \
        /var/spool/asterisk \
        /var/lib/teleblock \
        /var/log/teleblock

# Config will be volume-mounted at runtime (./asterisk → /etc/asterisk/teleblock)
VOLUME ["/var/lib/asterisk/sounds/teleblock", "/var/lib/teleblock", "/var/log/teleblock", "/var/log/asterisk"]

EXPOSE 5060/udp
EXPOSE 10000-20000/udp

USER asterisk

# Use -C to point directly at the teleblock config volume
# This avoids needing write access to /etc/asterisk/
CMD ["/usr/sbin/asterisk", "-f", "-C", "/etc/asterisk/teleblock/asterisk.conf", "-U", "asterisk", "-G", "asterisk"]
