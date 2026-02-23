#!/bin/bash
# Install/uninstall the system monitor launchd service

PLIST_NAME="com.trillium.system-monitor"
PLIST_SRC="$(dirname "$0")/${PLIST_NAME}.plist"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

case "${1:-install}" in
    install)
        cp "$PLIST_SRC" "$PLIST_DST"
        launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null
        launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
        echo "Installed and started $PLIST_NAME"
        ;;
    uninstall)
        launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null
        rm -f "$PLIST_DST"
        echo "Uninstalled $PLIST_NAME"
        ;;
    restart)
        launchctl bootout "gui/$(id -u)" "$PLIST_DST" 2>/dev/null
        launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"
        echo "Restarted $PLIST_NAME"
        ;;
    status)
        launchctl print "gui/$(id -u)/$PLIST_NAME" 2>&1
        ;;
    *)
        echo "Usage: $0 {install|uninstall|restart|status}"
        exit 1
        ;;
esac
