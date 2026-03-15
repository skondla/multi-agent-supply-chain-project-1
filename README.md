# Supply Chain AI Platform

> Production-grade multi-agent AI supply chain orchestration powered by Claude Opus 4.6

[![CI](https://github.com/your-org/supply-chain-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/supply-chain-ai/actions/workflows/ci.yml)
[![Security Scan](https://github.com/your-org/supply-chain-ai/actions/workflows/security-scan.yml/badge.svg)](https://github.com/your-org/supply-chain-ai/actions/workflows/security-scan.yml)
[![Coverage](https://codecov.io/gh/your-org/supply-chain-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/your-org/supply-chain-ai)

## Overview

A production-grade supply chain management platform built with 7 specialized AI agents coordinated by Claude Opus 4.6. The platform handles the complete supply chain lifecycle: order management, inventory control, supplier evaluation, logistics optimization, demand forecasting, and anomaly detection.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway (AWS ALB + WAF)               │
└─────────────────────────────┬───────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────┐
│                FastAPI (3-20 replicas, EKS)                  │
│                  ┌─────────────────┐                         │
│                  │  Orchestrator   │ ← Claude Opus 4.6       │
│                  │    Agent        │                         │
│                  └────────┬────────┘                         │
│         ┌─────────────────┼──────────────────┐              │
│         ▼                 ▼                  ▼              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │  Inventory  │  │    Order     │  │   Supplier    │      │
│  │   Agent     │  │    Agent     │  │    Agent      │      │
│  └─────────────┘  └──────────────┘  └───────────────┘      │
│         ▼                 ▼                  ▼              │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐      │
│  │  Logistics  │  │   Demand     │  │   Anomaly     │      │
│  │   Agent     │  │  Forecast    │  │  Detection    │      │
│  └─────────────┘  └──────────────┘  └───────────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

| Feature | Technology |
|---------|-----------|
| **Multi-Agent Orchestration** | Claude Opus 4.6 + Anthropic SDK |
| **API Framework** | FastAPI + Pydantic v2 |
| **Database** | Aurora PostgreSQL 15 (Multi-AZ) |
| **Caching** | ElastiCache Redis 7 |
| **Event Streaming** | Amazon MSK (Managed Kafka) |
| **ML Platform** | MLflow + XGBoost + scikit-learn |
| **Container Orchestration** | EKS 1.29 |
| **Infrastructure** | Terraform + AWS |
| **CI/CD** | GitHub Actions |
| **Monitoring** | Prometheus + Grafana + Jaeger |
| **Security** | OWASP, Trivy, Semgrep, CodeQL |

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- AWS CLI (for deployment)

### Local Development

```bash
# 1. Clone and configure
git clone https://github.com/your-org/supply-chain-ai
cd supply-chain-ai
cp .env.example .env

# 2. Add your Anthropic API key to .env
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" >> .env

# 3. Start all services
docker-compose up -d

# 4. Wait for services to be healthy
docker-compose ps

# 5. Run database migrations
docker-compose exec api alembic upgrade head

# 6. Verify it's working
curl http://localhost:8000/health
```

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Unit tests (fast, no external deps)
pytest tests/unit/ -v --cov=app --cov=agents --cov-report=html

# Integration tests (requires Docker Compose)
pytest tests/integration/ -v

# E2E smoke tests (requires running app)
API_BASE_URL=http://localhost:8000 pytest tests/e2e/ -v -m smoke

# Load tests
locust -f tests/load/locustfile.py --host=http://localhost:8000
```

## AI Agents

| Agent | Role | Tools |
|-------|------|-------|
| **OrchestratorAgent** | Routes tasks, coordinates agents | analyze_task, route_to_agent, aggregate_results |
| **InventoryAgent** | Stock management, reordering | check_inventory_level, calculate_reorder_quantity, reserve_inventory |
| **OrderAgent** | Order validation, fraud detection | validate_order, check_fraud_indicators, calculate_order_total |
| **SupplierAgent** | Vendor evaluation, RFQs | get_supplier_performance, evaluate_supplier, generate_rfq |
| **LogisticsAgent** | Carrier selection, tracking | select_carrier, track_shipment, handle_exception |
| **DemandForecastAgent** | ML demand prediction | get_demand_forecast, analyze_demand_trends, generate_replenishment_plan |
| **AnomalyDetectionAgent** | Fraud & anomaly detection | detect_order_anomalies, score_transaction, classify_anomaly |

## API Documentation

Once running, access the interactive API docs:

- **Swagger UI**: http://localhost:8000/api/docs
- **ReDoc**: http://localhost:8000/api/redoc
- **OpenAPI JSON**: http://localhost:8000/api/openapi.json

## Monitoring

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin/admin |
| Prometheus | http://localhost:9090 | - |
| Jaeger | http://localhost:16686 | - |
| MLflow | http://localhost:5000 | - |
| Kafka UI | http://localhost:8080 | - |
| PgAdmin | http://localhost:5050 | admin@supply-chain.local/admin |

## Deploying to AWS

### Infrastructure

```bash
cd infrastructure/terraform
terraform init
terraform workspace new production
terraform plan -var-file=environments/production.tfvars
terraform apply -var-file=environments/production.tfvars
```

### Application

```bash
# Set image tag
export IMAGE_TAG=v1.0.0
export ECR_REGISTRY=123456789.dkr.ecr.us-east-1.amazonaws.com

# Build and push
docker build -t $ECR_REGISTRY/supply-chain-api:$IMAGE_TAG .
docker push $ECR_REGISTRY/supply-chain-api:$IMAGE_TAG

# Deploy to EKS
./scripts/deploy.sh production $IMAGE_TAG
```

## CI/CD Pipelines

| Workflow | Trigger | Steps |
|----------|---------|-------|
| **CI** | Push/PR | Lint → Unit Tests → Integration Tests |
| **Security Scan** | Push/Schedule | OWASP → Semgrep → Gitleaks → Bandit → CodeQL |
| **Image Scan** | Push | Trivy → Snyk → Docker Scout → Hadolint |
| **CD Production** | Tag `v*.*.*` | Build → Scan → Deploy → Verify |
| **Terraform** | Infra changes | Validate → Plan → Apply |
| **MLOps** | Weekly/Dispatch | Data Validate → Train → Evaluate → Register |

## Security

This application implements OWASP Top 10 protections:

- **A01 Broken Access Control**: JWT authentication, RBAC
- **A02 Cryptographic Failures**: TLS everywhere, bcrypt passwords, KMS encryption
- **A03 Injection**: Parameterized queries via SQLAlchemy ORM
- **A04 Insecure Design**: Threat modeling, security headers
- **A05 Security Misconfiguration**: Hardened containers, security headers
- **A06 Vulnerable Components**: Automated dependency scanning (OWASP, Snyk)
- **A07 Auth Failures**: JWT with expiry, refresh tokens, bcrypt
- **A08 Software Integrity**: Image signing, SBOM
- **A09 Logging Failures**: Structured logging, audit trails
- **A10 SSRF**: URL validation, private network restrictions

## LLMOps & AIOps

- **Prompt Registry**: Versioned prompts with A/B testing support
- **Cost Tracking**: Per-agent token consumption and cost attribution
- **Guardrails**: Prompt injection detection, output filtering, rate limiting
- **Drift Detection**: Automated data drift monitoring with retraining triggers
- **Auto-Remediation**: Intelligent alert routing and automated runbook execution

## License

Proprietary - All rights reserved.


### Directories and Files in this project

```
├── agents
│   ├── __init__.py
│   ├── anomaly_detection_agent.py
│   ├── base_agent.py
│   ├── demand_forecast_agent.py
│   ├── inventory_agent.py
│   ├── logistics_agent.py
│   ├── orchestrator_agent.py
│   ├── order_agent.py
│   └── supplier_agent.py
├── aiops
│   ├── __init__.py
│   ├── automation
│   │   └── auto_remediation.py
│   ├── log_analysis
│   ├── monitoring
│   │   └── drift_detector.py
│   └── runbooks
├── alembic
│   ├── env.py
│   └── versions
│       └── 001_initial_schema.py
├── alembic.ini
├── app
│   ├── __init__.py
│   ├── api
│   │   ├── __init__.py
│   │   └── v1
│   │       ├── __init__.py
│   │       ├── endpoints
│   │       │   ├── __init__.py
│   │       │   ├── agents.py
│   │       │   ├── analytics.py
│   │       │   ├── auth.py
│   │       │   ├── inventory.py
│   │       │   ├── orders.py
│   │       │   ├── shipments.py
│   │       │   └── suppliers.py
│   │       └── router.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── kafka_client.py
│   │   ├── logging.py
│   │   ├── redis_client.py
│   │   ├── security.py
│   │   └── slack_notifier.py
│   ├── main.py
│   ├── middleware
│   │   ├── __init__.py
│   │   ├── request_id.py
│   │   └── security.py
│   ├── models
│   │   ├── __init__.py
│   │   ├── inventory.py
│   │   ├── order.py
│   │   ├── shipment.py
│   │   ├── supplier.py
│   │   └── user.py
│   ├── schemas
│   │   ├── __init__.py
│   │   ├── agent.py
│   │   ├── inventory.py
│   │   ├── order.py
│   │   └── supplier.py
│   ├── services
│   │   ├── __init__.py
│   │   └── order_service.py
│   └── tasks
│       ├── __init__.py
│       ├── celery_app.py
│       └── supply_chain_tasks.py
├── docker-compose.yml
├── Dockerfile
├── docs
│   ├── api
│   │   └── openapi.yaml
│   └── architecture
│       └── supply-chain-architecture.drawio
├── infrastructure
│   ├── kubernetes
│   │   ├── configmaps
│   │   │   └── app-config.yaml
│   │   ├── cronjobs
│   │   ├── deployments
│   │   │   ├── api-deployment.yaml
│   │   │   └── worker-deployment.yaml
│   │   ├── helm
│   │   │   ├── supply-chain-api
│   │   │   │   └── Chart.yaml
│   │   │   └── templates
│   │   ├── hpa
│   │   │   └── api-hpa.yaml
│   │   ├── ingress
│   │   │   └── ingress.yaml
│   │   ├── jobs
│   │   │   └── db-migration-job.yaml
│   │   ├── monitoring
│   │   ├── namespaces
│   │   │   └── namespace.yaml
│   │   ├── network-policies
│   │   │   └── network-policy.yaml
│   │   ├── pdb
│   │   │   └── pdb.yaml
│   │   ├── rbac
│   │   │   └── rbac.yaml
│   │   ├── secrets
│   │   ├── services
│   │   │   └── api-service.yaml
│   │   └── storage
│   └── terraform
│       ├── environments
│       │   ├── development.tfvars
│       │   ├── production.tfvars
│       │   └── staging.tfvars
│       ├── main.tf
│       ├── modules
│       │   ├── ecr
│       │   │   ├── main.tf
│       │   │   ├── outputs.tf
│       │   │   └── variables.tf
│       │   ├── eks
│       │   │   ├── main.tf
│       │   │   ├── outputs.tf
│       │   │   └── variables.tf
│       │   ├── elasticache
│       │   │   ├── main.tf
│       │   │   ├── outputs.tf
│       │   │   └── variables.tf
│       │   ├── msk
│       │   │   ├── main.tf
│       │   │   ├── outputs.tf
│       │   │   └── variables.tf
│       │   ├── rds
│       │   │   ├── main.tf
│       │   │   ├── outputs.tf
│       │   │   └── variables.tf
│       │   ├── s3
│       │   └── vpc
│       │       ├── main.tf
│       │       ├── outputs.tf
│       │       └── variables.tf
│       ├── outputs.tf
│       └── variables.tf
├── llmops
│   ├── __init__.py
│   ├── cost_tracker.py
│   ├── eval
│   │   └── test_cases
│   ├── guardrails.py
│   ├── prompt_registry.py
│   └── prompts
│       └── orchestrator.json
├── ml
│   ├── anomaly_detection
│   │   ├── __init__.py
│   │   └── train.py
│   ├── config
│   ├── data
│   ├── demand_forecast
│   │   ├── __init__.py
│   │   └── train.py
│   ├── monitoring
│   └── scripts
├── monitoring
│   ├── alertmanager
│   │   ├── alertmanager.yml
│   │   └── templates
│   │       └── slack.tmpl
│   ├── grafana
│   │   ├── dashboards
│   │   └── provisioning
│   │       ├── dashboards
│   │       │   └── dashboard.yaml
│   │       └── datasources
│   │           └── prometheus.yaml
│   ├── opentelemetry
│   └── prometheus
│       ├── prometheus.yml
│       └── rules
│           ├── api-alerts.yml
│           ├── infrastructure-alerts.yml
│           └── ml-alerts.yml
├── pyproject.toml
├── pytest.ini
├── README.md
├── requirements-dev.txt
├── requirements.txt
├── scripts
│   ├── deploy.sh
│   ├── init.sql
│   └── seed_data.py
├── security
└── tests
    ├── __init__.py
    ├── conftest.py
    ├── e2e
    │   ├── __init__.py
    │   └── test_smoke.py
    ├── integration
    │   └── __init__.py
    ├── load
    │   └── locustfile.py
    └── unit
        ├── __init__.py
        ├── test_agents.py
        └── test_models.py

80 directories, 129 files
```