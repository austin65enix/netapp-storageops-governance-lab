#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="/opt/netapp-storageops-lab"
METRICS_CONTRACT="${PROJECT_DIR}/docs/observability/metrics-contract.md"
ADR_FILE="${PROJECT_DIR}/docs/observability/ADR-001-prometheus-observability.md"

cd "$PROJECT_DIR"

test -f "$METRICS_CONTRACT"
echo "METRICS_CONTRACT_EXISTS=PASS"

test -f "$ADR_FILE"
echo "PROMETHEUS_ADR_EXISTS=PASS"

required_metrics=(
  storageops_info
  storageops_up
  storageops_ontap_up
  storageops_http_requests_total
  storageops_http_responses_total
  storageops_http_request_duration_seconds
  storageops_ontap_requests_total
  storageops_ontap_errors_total
  storageops_inventory_objects
  storageops_capacity_bytes
  storageops_volume_utilization_percent
  storageops_snapshot_runs_total
  storageops_diff_events_total
)

for metric in "${required_metrics[@]}"; do
  grep -q "$metric" "$METRICS_CONTRACT"
  echo "${metric}=PASS"
done

grep -q "GET /metrics" "$METRICS_CONTRACT"
echo "METRICS_ENDPOINT_CONTRACT=PASS"

grep -q "prohibited" "$METRICS_CONTRACT"
echo "CARDINALITY_POLICY=PASS"

grep -q "must remain operational" "$ADR_FILE"
echo "OBSERVABILITY_DECOUPLING_POLICY=PASS"

echo "NETAPP_M4_R1=PASS"
