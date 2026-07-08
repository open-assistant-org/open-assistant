#!/bin/sh
# WhatsApp bridge launcher.

# Run from the bridge directory so `node server.js` resolves from any cwd.
cd "$(dirname "$0")" || exit 1

# Managed mode: the bridge isn't used, so exit cleanly.
if [ -n "$MANAGED_API_KEY" ]; then
    echo "WhatsApp bridge disabled in managed mode"
    exit 0
fi

# Headless Chrome >=114 needs a DBus system bus to launch; without one it dies
# with "Code: null". Start a private, user-owned bus and point Chrome at it.
RUNTIME_DIR="/tmp/wa-bridge-runtime"
DBUS_SOCK="$RUNTIME_DIR/dbus"
DBUS_ADDR="unix:path=$DBUS_SOCK"
if command -v dbus-daemon >/dev/null 2>&1; then
    mkdir -p "$RUNTIME_DIR"
    chmod 700 "$RUNTIME_DIR"
    # dbus-daemon --session needs XDG_RUNTIME_DIR owned by us and mode 700.
    export XDG_RUNTIME_DIR="$RUNTIME_DIR"
    rm -f "$DBUS_SOCK"
    dbus-daemon --session --nofork --nopidfile --address="$DBUS_ADDR" &
    for _ in 1 2 3 4 5 6 7 8 9 10; do
        [ -S "$DBUS_SOCK" ] && break
        sleep 0.2
    done
    if [ -S "$DBUS_SOCK" ]; then
        export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_ADDR"
        export DBUS_SESSION_BUS_ADDRESS="$DBUS_ADDR"
        echo "🚌 DBus bus ready at $DBUS_ADDR"
    else
        echo "⚠️  DBus bus did not come up; continuing without it"
    fi
else
    echo "⚠️  dbus-daemon not found; continuing without a DBus bus"
fi

exec node server.js
