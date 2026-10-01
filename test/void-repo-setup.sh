# Sync the xbps remote repo index so `xbps-query -R` can answer existence for the name sweep. The
# nonfree repo is enabled too: components that live there (nmap, unrar) `requires: void-repo-nonfree`
# in core. (Same setup as core's own xbps sweep in tools/namesweep.py.)
xbps-install -Syu xbps >/dev/null 2>&1
xbps-install -Sy void-repo-nonfree >/dev/null 2>&1
xbps-install -S >/dev/null 2>&1 || true
