# Incident Report: INC-2026-001

**Title:** Inventory Service Connection Pool Exhaustion — Production  
**Service:** inventory-service  
**Environment:** Production  
**Severity:** HIGH  
**Status:** Resolved  
**Date:** 2026-01-14  
**Duration:** 45 minutes (10:23 UTC — 11:08 UTC)  
**Responders:** James Rodriguez (Platform Engineering), Maria Santos (Database Engineering)  

---

## Summary

On January 14, 2026, the inventory-service experienced connection pool exhaustion in production, causing readiness probe failures on 3 of 5 pods. The root cause was a memory leak in the HikariCP connection pool manager introduced in version 2.4.1 of the service. Connections were being borrowed but not properly returned during error handling paths in the inventory reservation flow.

## Timeline

| Time (UTC) | Event |
|------------|-------|
| 10:23 | `InventoryConnectionPoolExhausted` alert fires — `hikari_connections_pending > 10` on pods 1, 3, 4 |
| 10:25 | On-call engineer James Rodriguez acknowledges alert |
| 10:27 | Initial assessment: 3 of 5 pods showing readiness probe failures |
| 10:28 | Error rate climbed to 12.4% — checkout flow impacted |
| 10:30 | Metrics confirm: `hikari_connections_active = 50/50` on affected pods, `hikari_connections_idle = 0` |
| 10:32 | Decision: Rolling restart of unhealthy pods to clear leaked connections |
| 10:33 | Pod `inventory-service-7b8d9-xk2mv` deleted (1st restart) |
| 10:35 | Replacement pod Ready — verified connection pool healthy |
| 10:37 | Pod `inventory-service-7b8d9-rl4fn` deleted (2nd restart) |
| 10:39 | Replacement pod Ready — error rate dropping |
| 10:42 | Pod `inventory-service-7b8d9-qw9tz` deleted (3rd restart) |
| 10:44 | All pods healthy — error rate at 3.2% and declining |
| 10:48 | Error rate stabilized at 1.1% — below 5% threshold |
| 10:50 | Database Engineering confirmed no long-running queries or lock contention |
| 10:55 | Root cause identified: connection leak in `InventoryReservationService.reserveStock()` error handler |
| 11:00 | Hotfix PR created: added `finally` block to ensure connection release in all code paths |
| 11:05 | Hotfix deployed via canary (10% traffic) |
| 11:08 | Hotfix fully rolled out — incident resolved |

## Root Cause Analysis

### What Happened

The `InventoryReservationService.reserveStock()` method contained a bug in the error handling path. When a `StockInsufficientException` was thrown during the reservation process, the database connection was not returned to the HikariCP pool. This was because the connection release logic was in the success path but not in the `catch` block.

### Why It Happened

- The error handling path for `StockInsufficientException` was added in version 2.4.1 as part of a feature to provide better error messages to the checkout flow
- The developer used a manual connection management pattern instead of the project's standard `@Transactional` annotation
- Code review did not catch the missing connection release because the reviewer focused on the business logic, not resource management
- The leak was slow — approximately 1 connection leaked per 500 reservation failures, which took ~3 hours of peak traffic to exhaust the pool

### Code Fix

```java
// BEFORE (buggy)
public ReservationResult reserveStock(String productId, int quantity) {
    Connection conn = dataSource.getConnection();
    try {
        // ... reservation logic ...
        return new ReservationResult(true, reservationId);
    } catch (StockInsufficientException e) {
        // Connection NOT released here!
        return new ReservationResult(false, null, e.getMessage());
    }
}

// AFTER (fixed)
public ReservationResult reserveStock(String productId, int quantity) {
    Connection conn = dataSource.getConnection();
    try {
        // ... reservation logic ...
        return new ReservationResult(true, reservationId);
    } catch (StockInsufficientException e) {
        return new ReservationResult(false, null, e.getMessage());
    } finally {
        conn.close();  // Always return connection to pool
    }
}
```

## Impact

- **Duration of customer impact:** ~25 minutes (10:23 — 10:48)
- **Checkout success rate:** Dropped from 98.5% to 72.3% during the incident
- **Estimated revenue impact:** ~$45,000 in delayed/lost transactions
- **Affected users:** Approximately 1,200 customers experienced checkout errors
- **Data loss:** None — inventory state remained consistent
- **SLA impact:** Within monthly error budget (22 minutes of 22-minute monthly budget consumed)

## Remediation Actions Taken

1. **Immediate:** Rolling restart of 3 unhealthy pods (cleared leaked connections)
2. **Same day:** Hotfix deployed to fix the connection leak in `reserveStock()`
3. **Follow-up:** Added `@Transactional` annotation enforcement via static analysis rule

## Lessons Learned

### What Went Well

- Alert fired within 2 minutes of threshold breach
- On-call engineer responded within 2 minutes
- Rolling restart procedure was well-documented in runbook and executed smoothly
- Hotfix was deployed within 45 minutes of incident start

### What Could Be Improved

1. **Connection pool monitoring gap:** We had alerts on `hikari_connections_pending` but not on the rate of change of `hikari_connections_active`, which would have caught the slow leak earlier
2. **Code review process:** Resource management patterns should have explicit checklist items in code review
3. **Static analysis:** No linter rule existed to detect unclosed connections in catch blocks

## Follow-Up Actions

| Action | Owner | Status | Due Date |
|--------|-------|--------|----------|
| Add `hikari_connections_active` rate-of-change alert | James Rodriguez | ✅ Complete | 2026-01-21 |
| Add connection pool leak detection Grafana dashboard panel | Maria Santos | ✅ Complete | 2026-01-28 |
| Implement static analysis rule for unclosed connections | Platform Engineering | ✅ Complete | 2026-02-15 |
| Add connection pool integration test to CI pipeline | Platform Engineering | ✅ Complete | 2026-02-28 |
| Review all services for similar connection management patterns | Platform Engineering | ✅ Complete | 2026-03-15 |

## Tags

`connection-pool`, `hikari`, `memory-leak`, `inventory-service`, `production`, `checkout-impact`
