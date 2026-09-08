---
applyTo: "**/{scripts,deploy,systemd}/**,**/setup*.{py,sh},**/install*.sh"
description: "Raspberry Pi 5 deployment and hardware conventions for Teleblock. Use when writing setup scripts, systemd units, or deploy tooling."
---

# Raspberry Pi 5 — Deployment & Hardware Standards

## Target Platform
- **Board**: Raspberry Pi 5 (BCM2712, ARMv8-A 64-bit)
- **OS**: Raspberry Pi OS Bookworm (64-bit, headless server image)
- **Python**: System Python 3.11 via `python3`; use a `venv` at `/opt/teleblock/venv`
- **Asterisk**: 20 LTS — install from source or `apt` backport; confirm `pjsip` module is loaded

## Environment Setup
```bash
# Create venv and install deps
python3 -m venv /opt/teleblock/venv
source /opt/teleblock/venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Deploy code
sudo rsync -av --exclude='.env' ./ /opt/teleblock/app/

# Copy env
sudo cp .env /opt/teleblock/app/.env
sudo chmod 640 /opt/teleblock/app/.env
sudo chown root:asterisk /opt/teleblock/app/.env
```

## systemd Service Units
Place unit files in `systemd/` in the repo; symlink during deploy:
```bash
sudo ln -sf /opt/teleblock/app/systemd/teleblock-agi.service \
            /etc/systemd/system/teleblock-agi.service
sudo systemctl daemon-reload
sudo systemctl enable --now teleblock-agi
```

### FastAGI server unit template (`systemd/teleblock-agi.service`):
```ini
[Unit]
Description=Teleblock FastAGI Server
After=network.target asterisk.service
Requires=asterisk.service

[Service]
Type=simple
User=asterisk
Group=asterisk
WorkingDirectory=/opt/teleblock/app
EnvironmentFile=/opt/teleblock/app/.env
ExecStart=/opt/teleblock/venv/bin/python agi/server.py
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

## Networking
- Assign the Pi a **static IP** via router DHCP reservation (use MAC address)
- HT813 and Pi must be on the same LAN; configure HT813 SIP server = Pi's static IP
- Disable Wi-Fi if using Ethernet: `sudo rfkill block wifi`
- Open only required ports in `ufw`:
```bash
sudo ufw allow from 192.168.42.145 to any port 5060 proto udp  # SIP
sudo ufw allow from 192.168.42.145 to any port 10000:20000 proto udp  # RTP
sudo ufw deny 5060  # block WAN SIP
```

## Performance Tuning
- Disable unnecessary services: `sudo systemctl disable bluetooth hciuart`
- For SQLite on SD card, enable WAL mode: `PRAGMA journal_mode=WAL;`
- Set Asterisk real-time priority in `/etc/asterisk/asterisk.conf`:
  ```ini
  [options]
  rtprio = 50
  ```
- If using NVMe (PCIe HAT), update `/etc/fstab` with `noatime` mount option

## GPIO / Hardware Notes
- GPIO is not required for this build (audio goes via SIP/RTP, not GPIO)
- Do NOT use `RPi.GPIO` or `gpiozero` unless a future hardware indicator LED is added
- Power supply: use official Pi 5 27W USB-C PSU to prevent throttling under Asterisk + Python load

## Monitoring
- Use `journalctl -u teleblock-agi -f` to tail the AGI server log in real time
- Use `sudo asterisk -rvvv` to monitor live Asterisk calls
- Set up logrotate for `/var/log/teleblock/`:
```
/var/log/teleblock/*.log {
    daily
    rotate 14
    compress
    missingok
    notifempty
}
```

## Updating the System
```bash
# Pull latest code
cd /opt/teleblock/app && sudo git pull

# Reinstall deps if requirements changed
source /opt/teleblock/venv/bin/activate && pip install -r requirements.txt

# Restart service
sudo systemctl restart teleblock-agi

# Reload Asterisk dialplan (non-disruptive)
sudo asterisk -rx "dialplan reload"
```
