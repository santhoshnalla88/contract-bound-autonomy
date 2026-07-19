# Runbook: Inventory Service — Connection Pool Exhaustion

**Service:** inventory-service  
**Runbook ID:** RB-INV-001  
**Severity:** HIGH to CRITICAL  
**Owner:** Platform Engineering Team  
**Last Reviewed:** 2026-05-20  
**Approved By:** Sarah Chen, Principal SRE  

---

## Summary

This runbook covers the diagnosis and remediation of HikariCP connection pool exhaustion in the inventory-service. Connection pool exhaustion causes readiness probe failures, elevated error rates, and cascading timeouts that impact the checkout critical path.

## Symptoms

### Primary Indicators

- **Readiness probe failures:** Pods transition to `NotReady` state, Kubernetes removes them from the service endpoints
- **Elevated error rates:** HTTP 503 responses spike above 5% (SLO breach threshold)
- **Connection timeout errors in logs:** `HikariPool-1 - Connection is not available, request timed out after 30000ms`
- **Pending connection threads:** `hikari_connections_pending` metric exceeds 10 for sustained period (> 2 minutes)

### Secondary Indicators

- Increased P99 latency (> 100ms)
- Upstream services (order-service, storefront-bff) reporting increased error rates
- Redis cache hit rate may appear normal (issue is DB-side, not cache-side)
- Active connection count at or near maximum pool size (50 per pod)

### Alert Triggers

| Alert | Condition | Severity |
|-------|-----------|----------|
| `InventoryConnectionPoolExhausted` | `hikari_connections_pending > 10` for 2min | HIGH |
| `InventoryReadinessFailure` | `kube_pod_status_ready == 0` for > 1 pod | HIGH |
| `InventoryErrorRateHigh` | `error_rate > 5%` for 5min | CRITICAL |
| `InventoryAllPodsUnhealthy` | All pods `NotReady` | CRITICAL |

## Root Causes

### 1. Connection Leaks (Most Common)

- Application code fails to return connections to the pool after use
- Typically caused by missing `finally` blocks or unclosed `try-with-resources`
- HikariCP leak detection logs: `Apparent connection leak detected`
- **Remediation:** Rolling restart to clear leaked connections, then code fix

### 2. Traffic Spikes

- Sudden increase in requests (flash sale, marketing campaign)
- Connection pool sized for average load cannot handle burst
- All 50 connections per pod borrowed, new requests queue
- **Remediation:** Scale deployment to add more pods, distributing load

### 3. Long-Running Queries

- Slow queries hold connections longer than expected
- Common during database maintenance, index rebuilds, or lock contention
- Check `pg_stat_activity` for long-running transactions
- **Remediation:** Identify and terminate long-running queries, then restart affected pods

### 4. Pool Misconfiguration

- Maximum pool size too low for traffic volume
- Connection timeout too short for legitimate slow operations
- Idle timeout mismatch with PostgreSQL `idle_in_transaction_session_timeout`
- **Remediation:** Adjust HikariCP configuration via ConfigMap, rolling restart

## Remediation Procedure

### Step 1: Assess Current State

Check the current health status of the deployment:

```bash
kubectl get pods -n commerce-production -l app=inventory-service
kubectl top pods -n commerce-production -l app=inventory-service
```

Verify metrics:

```bash
# Check connection pool metrics
curl -s http://inventory-service.commerce-production:8080/metrics | grep hikari

# Key metrics to check:
# hikari_connections_active    — should be < 45 (90% of max)
# hikari_connections_idle      — should be > 5
# hikari_connections_pending   — should be 0; > 10 indicates exhaustion
# hikari_connections_timeout_total — check if increasing
```

Record current state for incident documentation.

### Step 2: Identify Unhealthy Pods

```bash
# List pods with readiness status
kubectl get pods -n commerce-production -l app=inventory-service \
  -o custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status,RESTARTS:.status.containerStatuses[0].restartCount

# Check events for crash/restart patterns
kubectl describe pod <pod-name> -n commerce-production
```

### Step 3: Restart Unhealthy Pods (Rolling)

**IMPORTANT:** Preserve active connections during restart. Do NOT delete all pods simultaneously.

Restart pods one at a time, waiting for each to become Ready before proceeding:

```bash
# Delete one unhealthy pod at a time
# Kubernetes will recreate it via the deployment
kubectl delete pod <unhealthy-pod-name> -n commerce-production

# Wait for replacement pod to be Ready (timeout 120s)
kubectl wait --for=condition=Ready pod -l app=inventory-service \
  -n commerce-production --timeout=120s
```

**Constraints:**
- Maximum 2 pod restarts per incident (per operational contract)
- Maintain at least 2 available replicas at all times
- If active checkout connections exist, enable connection draining before restart
- Wait 30 seconds between pod restarts to allow connection redistribution

### Step 4: Verify Recovery After Restarts

```bash
# Check pod health
kubectl get pods -n commerce-production -l app=inventory-service

# Verify connection pool recovered
curl -s http://inventory-service.commerce-production:8080/metrics | grep hikari_connections_pending
# Expected: hikari_connections_pending == 0

# Check error rate
# Expected: error_rate < 5% within 2 minutes of restart
```

If error rate remains above 5% after restarting unhealthy pods, proceed to Step 5.

### Step 5: Scale Deployment (If Restarts Insufficient)

If the issue is traffic-related rather than a connection leak:

```bash
# Scale up to distribute connection load
# Do NOT exceed 10 replicas (contract limit)
kubectl scale deployment inventory-service -n commerce-production --replicas=7

# Wait for new pods to be ready
kubectl rollout status deployment/inventory-service -n commerce-production --timeout=180s
```

**Constraints:**
- Maximum replicas: 10 (per operational contract)
- Maximum scale-up: 200% of current count
- Monitor database connection count: total connections = replicas × 50
  - At 10 replicas: 500 total connections (verify RDS max_connections supports this)

### Step 6: Verify Postconditions

After remediation, verify all postconditions are met:

1. **Healthy pod count ≥ 3:** `kubectl get pods -n commerce-production -l app=inventory-service --field-selector=status.phase=Running | wc -l`
2. **Error rate < 5%:** Check Grafana dashboard or Prometheus: `rate(http_requests_total{service="inventory-service",status=~"5.."}[5m]) / rate(http_requests_total{service="inventory-service"}[5m]) * 100`
3. **Connection pool healthy:** `hikari_connections_pending == 0` on all pods
4. **Upstream services recovered:** Check order-service and storefront-bff error rates

## Rollback Procedure

If the connection pool exhaustion was caused by a recent deployment:

```bash
# Check recent deployment history
kubectl rollout history deployment/inventory-service -n commerce-production

# Rollback to previous revision
kubectl rollout undo deployment/inventory-service -n commerce-production

# Monitor rollback
kubectl rollout status deployment/inventory-service -n commerce-production --timeout=180s
```

**Note:** Rollback requires human approval per operational contract.

## Escalation Criteria

Escalate to on-call Platform Engineering lead if:

- All pods are unhealthy simultaneously
- Error rate remains above 5% after two restart cycles
- Connection pool exhaustion recurs within 1 hour of remediation
- Database primary shows signs of failure (replication lag > 30s)
- Remediation requires actions not covered by the operational contract
- Customer-facing impact exceeds 10 minutes

### Escalation Path

1. **L1:** Platform Engineering on-call (PagerDuty)
2. **L2:** Database Engineering team (if DB-related root cause)
3. **L3:** VP Engineering (if revenue impact > $10K/minute)

## Related Documents

- [Inventory Service Architecture](../architecture/inventory-service-architecture.md)
- [Incident INC-2026-001: Connection Pool Exhaustion](../incidents/incident-2026-001.md)
- Operational Contract: `inventory-service-production-v1`
