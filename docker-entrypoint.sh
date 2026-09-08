#!/bin/sh
# Teleblock Asterisk container entrypoint.
# Patches /etc/asterisk/asterisk.conf and /etc/asterisk/musiconhold.conf
# to #include our teleblock configs, then hands off to the real Asterisk binary.
set -e

TELEBLOCK_CFG=/etc/asterisk/teleblock/asterisk.conf
MAIN_CFG=/etc/asterisk/asterisk.conf

if [ -f "$TELEBLOCK_CFG" ]; then
    # Append the teleblock include if not already present
    if ! grep -q "teleblock/asterisk.conf" "$MAIN_CFG" 2>/dev/null; then
        echo "" >> "$MAIN_CFG"
        echo "#include $TELEBLOCK_CFG" >> "$MAIN_CFG"
    fi
fi

# Patch musiconhold.conf to include our ringback MOH class
TELEBLOCK_MOH=/etc/asterisk/teleblock/musiconhold.conf
MOH_CFG=/etc/asterisk/musiconhold.conf

if [ -f "$TELEBLOCK_MOH" ]; then
    if ! grep -q "teleblock/musiconhold.conf" "$MOH_CFG" 2>/dev/null; then
        echo "" >> "$MOH_CFG"
        echo "#include $TELEBLOCK_MOH" >> "$MOH_CFG"
    fi
fi

# Patch logger.conf to include our teleblock logger config (sets queue_log=no
# and redirects persistent logs to /var/log/teleblock/ which is writable).
TELEBLOCK_LOG=/etc/asterisk/teleblock/logger.conf
LOG_CFG=/etc/asterisk/logger.conf

if [ -f "$TELEBLOCK_LOG" ]; then
    if ! grep -q "teleblock/logger.conf" "$LOG_CFG" 2>/dev/null; then
        echo "" >> "$LOG_CFG"
        echo "#include $TELEBLOCK_LOG" >> "$LOG_CFG"
    fi
fi

exec /usr/sbin/asterisk -f -U asterisk -G asterisk "$@"
