#!/usr/bin/env bash
# ==============================================================================
# Kubernetes Network Self-Healing & Chaos Engineering Scenarios
# Run this on your K3s control-plane node (or with kubectl configured)
# ==============================================================================
set -euo pipefail

function print_banner() {
  echo ""
  echo "======================================================================"
  echo "  $1"
  echo "======================================================================"
}

print_banner "K3s Self-Healing & Fault Tolerance Experiment Suite"

echo "Select an experiment to run:"
echo "  1) Pod Deletion & Recovery (Test DB Pod resurrection)"
echo "  2) Readiness Probe Network Trip (Simulate DB network failure)"
echo "  3) Worker Node Drain (Test Pod rescheduling & anti-affinity)"
echo "  4) View Live Cluster Topology & Pod Distribution"
echo "  q) Quit"
echo ""
read -rp "Enter choice [1-4]: " CHOICE

case "${CHOICE}" in
  1)
    print_banner "SCENARIO 1: Transient Database Failure & Automatic Healing"
    echo "Current Postgres Pod:"
    kubectl get pods -l app=postgres-db -o wide
    echo ""
    echo "-> Deleting Postgres Pod to simulate unexpected crash..."
    kubectl delete pod -l app=postgres-db --now
    echo "-> Monitoring pod recreation by Kubernetes Deployment controller..."
    kubectl get pods -l app=postgres-db -w
    ;;

  2)
    print_banner "SCENARIO 2: Readiness Probe Trip (Network Blackhole)"
    echo "-> Current Endpoint Slices for Backend API:"
    kubectl get endpoints backend-service
    echo ""
    echo "-> In a separate terminal, run ./test-traffic.sh to observe continuous requests."
    echo "-> Now scaling DB replicas to 0 to simulate complete DB network loss..."
    kubectl scale deployment postgres-db --replicas=0
    echo ""
    echo "-> Observe backend pods failing their readiness probes (transitioning to 0/1 Ready):"
    kubectl get pods -l app=backend-api -w &
    WATCH_PID=$!
    sleep 8
    kill ${WATCH_PID} 2>/dev/null || true
    echo ""
    echo "-> Checking backend Service endpoints (all pods should be removed from routing pool):"
    kubectl get endpoints backend-service
    echo ""
    read -rp "Press [Enter] to restore database and trigger self-healing..."
    kubectl scale deployment postgres-db --replicas=1
    echo "-> Waiting for PostgreSQL to become Ready..."
    kubectl wait --for=condition=ready pod -l app=postgres-db --timeout=60s
    echo "-> Backend pods will automatically pass readiness probes and rejoin endpoint pool:"
    kubectl get pods -l app=backend-api -w
    ;;

  3)
    print_banner "SCENARIO 3: Worker Node Drain & Pod Rescheduling"
    echo "Current Node Distribution of Backend Pods:"
    kubectl get pods -l app=backend-api -o wide
    echo ""
    read -rp "Enter the name of a worker node to drain: " TARGET_NODE
    echo "-> Cordoning and draining node ${TARGET_NODE}..."
    kubectl drain "${TARGET_NODE}" --ignore-daemonsets --delete-emptydir-data --force
    echo ""
    echo "-> Verifying pods moved safely to the remaining node(s):"
    kubectl get pods -l app=backend-api -o wide
    echo ""
    read -rp "Press [Enter] to uncordon node ${TARGET_NODE}..."
    kubectl uncordon "${TARGET_NODE}"
    echo "-> Node ${TARGET_NODE} is schedulable again."
    ;;

  4)
    print_banner "SCENARIO 4: Live Cluster Distribution"
    kubectl get nodes -o wide
    echo ""
    kubectl get pods -o wide --show-labels
    echo ""
    kubectl get svc -o wide
    ;;

  *)
    echo "Exiting."
    exit 0
    ;;
esac

