# Inventory Service — Architecture Document

**Service:** inventory-service  
**Owner:** Platform Engineering Team  
**Environment:** Production  
**Last Updated:** 2026-06-15  
**Status:** Active — Critical Path  

---

## Overview

The inventory-service is the core real-time inventory tracking system for the e-commerce platform. It manages stock levels, product availability, and inventory reservations across all fulfillment centers. It sits on the critical path for the checkout flow — any downtime directly blocks customer purchases and results in revenue loss.

## Infrastructure

### Kubernetes Deployment

- **Namespace:** `commerce-production`
- **Deployment:** `inventory-service`
- **Replicas:** 5 (default), auto-scaling disabled for stability
- **Resource Limits:**
  - CPU: 500m request / 1000m limit per pod
  - Memory: 512Mi request / 1Gi limit per pod
- **Image:** `registry.internal/commerce/inventory-service:latest`
- **Rolling Update Strategy:**
  - Max Surge: 1
  - Max Unavailable: 1

### Health Probes

- **Readiness Probe:**
  - HTTP GET `/health/ready` on port 8080
  - Initial delay: 10s, period: 5s, failure threshold: 3
  - Checks database connectivity and connection pool health
- **Liveness Probe:**
  - HTTP GET `/health/live` on port 8080
  - Initial delay: 30s, period: 10s, failure threshold: 5
  - Basic process liveness check

### Pod Disruption Budget

- **minAvailable:** 3
- Ensures at least 3 pods remain during voluntary disruptions

## Database Layer

### PostgreSQL

- **Instance:** `inventory-db-primary` (AWS RDS PostgreSQL 15.4)
- **Connection Pool:** HikariCP
  - Maximum pool size: 50 connections per pod
  - Minimum idle connections: 10
  - Connection timeout: 30,000ms (30 seconds)
  - Idle timeout: 600,000ms (10 minutes)
  - Max lifetime: 1,800,000ms (30 minutes)
  - Leak detection threshold: 60,000ms (60 seconds)
- **Read Replicas:** 2 replicas for read-heavy queries (stock lookups)
- **Database:** `inventory_production`
- **Key Tables:**
  - `inventory_items` (~2.5M rows) — current stock levels
  - `inventory_reservations` (~500K active) — checkout hold reservations
  - `inventory_transactions` (~50M rows) — audit trail

### Connection Pool Monitoring

- Metrics exposed at `/metrics` (Prometheus format)
- Key metrics:
  - `hikari_connections_active` — currently borrowed connections
  - `hikari_connections_idle` — available idle connections
  - `hikari_connections_pending` — threads waiting for a connection
  - `hikari_connections_timeout_total` — cumulative connection timeouts
- Alert threshold: `hikari_connections_pending > 10` for 2 minutes

## Cache Layer

### Redis

- **Cluster:** `inventory-cache` (AWS ElastiCache Redis 7.0, 3-node cluster)
- **Purpose:** Product availability cache for high-frequency lookups
- **TTL:** 30 seconds for availability data, 5 minutes for catalog metadata
- **Cache-aside pattern:** Read from cache → miss → read from DB → populate cache
- **Eviction Policy:** `allkeys-lru`
- **Max Memory:** 2GB per node

## Service Dependencies

### Upstream (services that call inventory-service)

| Service | Protocol | Description |
|---------|----------|-------------|
| order-service | gRPC | Stock reservation during checkout |
| storefront-bff | REST | Product availability display |

### Downstream (services inventory-service calls)

| Service | Protocol | Description |
|---------|----------|-------------|
| payment-service | gRPC | Payment confirmation triggers stock deduction |
| product-catalog-service | gRPC | Product metadata enrichment |
| notification-service | async (Kafka) | Low-stock alerts to warehouse |

### Inter-Service Communication

- **Protocol:** gRPC with TLS mutual authentication
- **Service Mesh:** Istio sidecar proxy
- **Timeout:** 5s default, 10s for batch operations
- **Retry Policy:** 2 retries with exponential backoff (100ms base)
- **Circuit Breaker:** 50% error rate threshold, 30s recovery window

## Traffic Patterns

- **Average RPS:** ~2,000 requests/second
- **Peak RPS:** ~8,000 requests/second (flash sales, Black Friday)
- **P99 Latency:** 45ms (target), 100ms (SLO breach threshold)
- **Daily Pattern:** Traffic ramps from 6 AM, peaks at 12 PM and 8 PM EST

## Critical Path Impact

The inventory-service is on the **critical path for checkout**:

1. Customer adds item to cart → `storefront-bff` checks availability via inventory-service
2. Customer initiates checkout → `order-service` reserves stock via inventory-service
3. Payment confirmed → `payment-service` notifies inventory-service to deduct stock
4. If inventory-service is down, steps 1-3 are blocked, causing checkout failures

**SLA:** 99.95% availability (allows ~22 minutes downtime/month)

## Failure Modes

| Failure Mode | Impact | Detection | Mitigation |
|-------------|--------|-----------|------------|
| Connection pool exhaustion | Readiness probe fails, pods marked unhealthy | `hikari_connections_pending > 10` | Rolling pod restart |
| Database primary failure | All writes fail | RDS multi-AZ failover alarm | Automatic RDS failover (~30s) |
| Redis cache failure | Increased DB load, higher latency | Cache hit rate drops below 80% | Graceful degradation to DB-only |
| Memory leak | OOMKilled pods | Container memory usage > 90% | Pod restart, investigate heap dump |

## Deployment

- **CI/CD:** GitHub Actions → ArgoCD GitOps
- **Rollback:** ArgoCD revision rollback (< 60 seconds)
- **Feature Flags:** LaunchDarkly for gradual rollouts
- **Canary:** 10% traffic to canary pod for 15 minutes before full rollout
