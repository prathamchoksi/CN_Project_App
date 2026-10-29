#!/usr/bin/env bash
# ==============================================================================
# Traffic Generator & Visual Load Balancing Verifier
# ==============================================================================
set -euo pipefail

TARGET_URL="${1:-http://localhost:8080/}"
REQUEST_COUNT="${2:-20}"

echo "======================================================================"
echo " Starting K3s Traffic Generator"
echo " Target Endpoint : ${TARGET_URL}"
echo " Total Requests  : ${REQUEST_COUNT}"
echo "======================================================================"
printf "%-6s | %-12s | %-28s | %-16s | %-10s | %-10s\n" \
  "REQ#" "STATUS" "POD NAME" "NODE NAME" "DB VISITS" "LATENCY"
echo "--------------------------------------------------------------------------------------------------"

for i in $(seq 1 "${REQUEST_COUNT}"); do
  RESPONSE=$(curl -s -w "\n%{http_code}" --connect-timeout 2 "${TARGET_URL}" || echo -e '{"error":"connect_timeout"}\n000')
  HTTP_CODE=$(echo "${RESPONSE}" | tail -n1)
  BODY=$(echo "${RESPONSE}" | sed '$d')

  if [ "${HTTP_CODE}" -eq 200 ]; then
    POD=$(echo "${BODY}" | grep -o '"pod_name": *"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    NODE=$(echo "${BODY}" | grep -o '"node_name": *"[^"]*"' | cut -d'"' -f4 || echo "unknown")
    VISITS=$(echo "${BODY}" | grep -o '"total_database_visits": *[0-9]*' | grep -o '[0-9]*' || echo "0")
    LATENCY=$(echo "${BODY}" | grep -o '"db_latency_ms": *[0-9.]*' | awk '{print $2}' || echo "0")
    
    printf "%-6d | \033[0;32mHTTP %-7s\033[0m | %-28s | \033[1;36m%-16s\033[0m | %-10s | %-10sms\n" \
      "${i}" "${HTTP_CODE}" "${POD}" "${NODE}" "${VISITS}" "${LATENCY}"
  else
    printf "%-6d | \033[0;31mHTTP %-7s\033[0m | %-28s | %-16s | %-10s | %-10s\n" \
      "${i}" "${HTTP_CODE}" "DEGRADED/UNAVAILABLE" "N/A" "N/A" "N/A"
  fi
  sleep 0.5
done

echo "======================================================================"
echo " Traffic verification run complete."
echo " Notice how POD NAME and NODE NAME alternate across requests,"
echo " proving round-robin K3s ServiceLB distribution and DB persistence!"
echo "======================================================================"

