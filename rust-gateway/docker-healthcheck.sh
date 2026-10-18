#!/bin/sh
set -eu

# Host-network staging Compose overrides this port with its loopback gateway
# listener. The standalone image remains healthy on its normal container port.
port="${AN3_GATEWAY_HEALTHCHECK_PORT:-8093}"
case "$port" in
  ''|*[!0-9]*) exit 1 ;;
esac

exec curl --fail --silent --show-error "http://127.0.0.1:${port}/health"
