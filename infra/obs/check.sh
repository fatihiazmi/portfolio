#!/bin/sh
# Check the Prometheus config and rules, and run the rule unit tests. Plan T20.
# Needs Docker. Run from anywhere: infra/obs/check.sh
set -eu
cd "$(dirname "$0")"
img=prom/prometheus:v3.15.1
run() { docker run --rm --entrypoint promtool -v "$PWD:/obs:ro" -w /obs "$img" "$@"; }
# --syntax-only: the config names rule files by their in-container path, /etc/prometheus.
run check config --syntax-only prometheus/prometheus.yml
run check rules prometheus/rules/*.yml
run test rules tests/*.test.yml
