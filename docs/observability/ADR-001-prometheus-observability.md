# ADR-001 Prometheus Observability

## Status

Accepted

## Context

The StorageOps runtime is managed by systemd and already provides health,
dependency failure handling, recovery, and deployment evidence.

Health checks alone do not provide historical request, latency, capacity,
or dependency failure information.

## Decision

The StorageOps API will expose Prometheus-compatible metrics through:

GET /metrics

Prometheus will scrape the API locally.

Grafana will query Prometheus and provide the operational dashboard.

## Dependency Model

StorageOps API -> Prometheus -> Grafana

The StorageOps API must remain operational when Prometheus or Grafana is
unavailable.

Prometheus and Grafana are observability consumers, not runtime dependencies
of the StorageOps API.

## Security Boundary

The first lab implementation binds Prometheus and Grafana to the lab network.

Production deployment must add:

- network access control
- authentication
- TLS termination
- secret management
- restricted administrative access

## Consequences

Benefits:

- standard metric format
- historical trend visibility
- alert rule support
- reusable dashboards
- infrastructure-independent observability

Costs:

- additional runtime services
- storage retention requirements
- metric cardinality governance
- dashboard and alert maintenance
