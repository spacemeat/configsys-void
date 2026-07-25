# Sync the xbps remote repo index so `xbps-query -R` can answer existence for the name sweep.
# The void-glibc image ships the default repos configured; just refresh the index.
xbps-install -Sy >/dev/null 2>&1 || xbps-install -S >/dev/null 2>&1 || true
