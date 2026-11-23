#!/bin/bash
# Install/uninstall the system monitor service.
# macOS: launchd agent. Linux: systemd user unit.

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"

case "$(uname -s)" in
    Darwin)
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
        ;;
    Linux)
        UNIT_NAME="system-monitor.service"
        UNIT_SRC="$REPO_DIR/$UNIT_NAME"
        UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
        UNIT_DST="$UNIT_DIR/$UNIT_NAME"

        case "${1:-install}" in
            install)
                mkdir -p "$UNIT_DIR"
                sed "s|@REPO_DIR@|$REPO_DIR|g" "$UNIT_SRC" > "$UNIT_DST"
                systemctl --user daemon-reload
                systemctl --user enable "$UNIT_NAME"
                systemctl --user restart "$UNIT_NAME"
                echo "Installed and started $UNIT_NAME"
                ;;
            uninstall)
                systemctl --user disable --now "$UNIT_NAME" 2>/dev/null
                rm -f "$UNIT_DST"
                systemctl --user daemon-reload
                echo "Uninstalled $UNIT_NAME"
                ;;
            restart)
                systemctl --user restart "$UNIT_NAME"
                echo "Restarted $UNIT_NAME"
                ;;
            status)
                systemctl --user status "$UNIT_NAME" --no-pager 2>&1
                ;;
            *)
                echo "Usage: $0 {install|uninstall|restart|status}"
                exit 1
                ;;
        esac
        ;;
    *)
        echo "Unsupported OS: $(uname -s)"
        exit 1
        ;;
esac
