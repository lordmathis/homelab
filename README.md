# Homelab

Local LLM inference and other apps on Mac Mini M4 Pro

## llamactl launchd

1. Symlink the plist file to `$HOME/Library/LaunchAgents/com.llamactl.plist`
   ```bash
   ln -sf $HOME/homelab/com.llamactl.plist $HOME/Library/LaunchAgents/com.llamactl.plist
   ```

2. Load the plist filr
   ```bash
   launchctl load $HOME/Library/LaunchAgents/com.llamactl.plist
   ```

3. Start and stop the service
   ```bash
   # Start the service manually (if not running)
   launchctl start com.llamactl

   # Stop the service
   launchctl stop com.llamactl
   ```