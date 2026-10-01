# TradeForge Infrastructure (`infra/`)

Deployment configurations, container definitions, and telemetry:
- `docker/`: Multi-stage Dockerfiles for Python backend services and Next.js frontend.
- `k8s/`: Production Kubernetes manifests (Deployments, StatefulSets, Secrets, Ingress).
- `monitoring/`: Prometheus metric scraping rules and Grafana dashboards for order latency, rejection rate, and P&L tracking.
