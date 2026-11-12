# 🌳 BigTree (ดูไบไม้ — Dubaimai)
### CS341 Big Data Engineering Project: Urban Green Space & Ambient Temperature Analysis

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Package Manager: uv](https://img.shields.io/badge/Managed%20by-uv-purple.svg)](https://github.com/astral-sh/uv)
[![IaC: Terraform](https://img.shields.io/badge/IaC-Terraform-7B42BC.svg)](https://www.terraform.io/)
[![Cloud: AWS Serverless](https://img.shields.io/badge/AWS-Step%20Functions%20%2B%20Lambda-FF9900.svg)](https://aws.amazon.com/)
[![Tests: 38 Passed](https://img.shields.io/badge/Tests-38%20Passed%20(100%25)-brightgreen.svg)]()

An automated, rerunnable, and idempotent Big Data pipeline that studies the relationship between urban green space indicators and ambient air temperature across Bangkok's 50 administrative districts.

---

## 🏛️ Pipeline Architecture

The pipeline implements **Hexagonal (Clean) Architecture**, strictly isolating pure domain business rules from external I/O and cloud infrastructure.

```mermaid
flowchart TD
    subgraph S1["1. INGESTION (Person 1)"]
        OM["Open-Meteo Historical API"] -->|Hourly Temps| L1["Lambda: Weather Ingestion"]
        L1 -->|Preserved JSONs| S3Raw[("s3://dubaimai/raw/weather/")]
    end

    subgraph S2["2. SPATIAL PREPROCESSING (Person 2)"]
        KML["BMA District KML / GeoJSON"] -->|Centroid Calculation| S3Spatial[("s3://dubaimai/spatial/")]
    end

    subgraph S3["3. TRANSFORMATION & QUALITY RULES (Person 3)"]
        S3Raw & S3Spatial & GreenCSV[("s3://dubaimai/data/green_space.csv")] --> L2["Lambda: Data Transformation"]
        L2 -->|Domain Business Rules| Split{"Pass Quality Rules?"}
        Split -->|Yes| S3Curated[("s3://dubaimai/curated/district_analysis.csv")]
        Split -->|No (Recorded Reasons)| S3NotPass[("s3://dubaimai/not_pass/rejected_records.csv")]
    end

    subgraph S4["4. STATISTICAL RESEARCH & VIZ (Person 4)"]
        S3Curated --> L3["Lambda: Research Analysis"]
        L3 --> Q1["Q1: Temporal Trajectory"]
        L3 --> Q2["Q2: High vs Low Green Space"]
        L3 --> Q3["Q3: Bivariate Correlation"]
        L3 --> S3Reports[("s3://dubaimai/reports/")]
    end

    SFN["AWS Step Functions State Machine"] -.->|Orchestrates| L1
    SFN -.->|Orchestrates| L2
    SFN -.->|Orchestrates| L3
```

---

## 🔬 Research Questions Addressed

* **Q1 (Temporal Trajectory)**: Analyzes diurnal cycle peaks (afternoon heat vs. dawn cooling) and computes Diurnal Temperature Range (DTR) across districts.
* **Q2 (Group Comparison)**: Evaluates whether high-green space districts are statistically significantly cooler than low-green space districts using independent $t$-tests and non-parametric Mann-Whitney U tests ($\alpha = 0.05$).
* **Q3 (Correlation & Regression)**: Calculates Pearson $r$, Spearman $\rho$, and OLS regression slope/intercept with academic disclaimers on confounders (correlation $\neq$ causation).

---

## ⚡ Quickstart: Local Execution (Zero-Setup)

The project is fully managed using `uv` and includes an automatic `.s3_mock/` local storage layer so the entire pipeline runs seamlessly offline without requiring active AWS credentials.

### 1. Prerequisites & Installation

```bash
# Clone the repository
git clone https://github.com/Kanna-Sama89/BigTree.git
cd BigTree

# Install dependencies and sync virtual environment
uv sync
```

### 2. Run the Full End-to-End Pipeline Locally

```bash
# Run all stages: Ingestion -> Transformation -> Statistical Analysis
uv run python -m bigtree.entrypoints.cli all

# Or run individual stages:
uv run python -m bigtree.entrypoints.cli ingest --start-date 2023-04-01 --end-date 2023-04-30
uv run python -m bigtree.entrypoints.cli transform
uv run python -m bigtree.entrypoints.cli analyze
```

Generated charts will appear in `reports/visualizations/`:
* `q1_temperature_distribution.png`
* `q2_cohort_comparison.png`
* `q3_correlation_scatter.png`

---

## 🧪 Testing & Verification

All domain business rules, use cases, and spatial processing tests are **100% hermetic** and execute with zero external network calls.

```bash
# Run all 38 unit and integration tests
uv run pytest -v

# Run domain rules & idempotency tests specifically
uv run pytest tests/test_domain_rules.py tests/test_rerunnability.py
```

---

## 🚀 AWS Cloud Deployment (Terraform)

All AWS infrastructure is codified in the `terraform/` directory.

### Provisioned Cloud Resources:
* **Amazon S3 Data Lake**: Secure bucket with versioning, AES256 server-side encryption, and public access block.
* **3 AWS Lambda Functions**: Python 3.12 runtime powered by the official AWS SDK Pandas managed layer.
* **AWS Step Functions State Machine**: Manages the multi-stage pipeline with automated retries and backoff.
* **AWS EventBridge**: Optional cron scheduler for automatic recurring ingestion.

### Deployment Steps:

```bash
cd terraform

# 1. Initialize Terraform providers (AWS, Archive, Random)
terraform init

# 2. Preview the deployment plan
terraform plan

# 3. Deploy the infrastructure to AWS
terraform apply -auto-approve
```

### Triggering the Pipeline in AWS:

Once deployed, trigger the entire pipeline with one command:

```bash
aws stepfunctions start-execution \
  --region ap-southeast-1 \
  --state-machine-arn $(terraform output -raw step_functions_state_machine_arn) \
  --input "{\"bucket_name\":\"$(terraform output -raw s3_bucket_name)\"}"
```

### Teardown:

```bash
terraform destroy -auto-approve
```

---

## 📁 Repository Structure

```text
BigTree/
├── data/                               # Input datasets (districts KML, GeoJSON, green space CSV)
│   ├── bangkok_districts.kml
│   ├── district_coordinates.csv        # 50 Bangkok district representative coordinates
│   └── green_space.csv                 # District green area (sqm) and park counts
├── reports/visualizations/             # Generated statistical figures (Q1-Q3)
├── src/bigtree/
│   ├── domain/                         # Pure Business Rules & Domain Entities (Zero I/O)
│   │   ├── models.py                   # Dataclasses & Value Objects
│   │   ├── rules.py                    # Temperature & Green Space Quality Rules
│   │   └── statistics.py               # Statistical formulas (DTR, Mann-Whitney, OLS)
│   ├── use_cases/                      # Application Services & Orchestrators
│   │   ├── transform_and_validate.py   # Person 3 Transform Use Case
│   │   └── analyze_research_questions.py # Person 4 Analysis Use Case (Q1-Q3)
│   ├── ports/                          # Abstract storage & component interfaces
│   ├── adapters/                       # S3 and In-Memory Storage Adapters
│   ├── ingestion/                      # Person 1 Open-Meteo Ingestion Client
│   ├── spatial/                        # Person 2 Boundary & Centroid Processing
│   └── entrypoints/                    # Lambda Handlers and Unified CLI
├── terraform/                          # Infrastructure as Code
│   ├── main.tf                         # S3 Data Lake & Lambda Functions
│   ├── step_functions.tf               # AWS Step Functions State Machine
│   ├── variables.tf                    # Configurable parameters & region
│   ├── outputs.tf                      # Exported ARNs & CLI commands
│   └── versions.tf                     # Provider requirements
├── tests/                              # Comprehensive Hermetic Test Suite (38 tests)
├── pyproject.toml                      # Project metadata & dependencies
└── README.md
```

---

## 👥 Contributors (Team Dubaimai)

* **Person 1 (การิน)**: Weather Data Ingestion (Open-Meteo API Client, S3 Storage, Fault-Tolerant Batching).
* **Person 2 (ฮาซัน)**: Spatial Data Preprocessing (BMA District KML parsing, CRS reprojection, Centroid calculation).
* **Person 3 (ธีทัต)**: Data Transformation & Validation (Clean Architecture Quality Rules, Curated vs. Not Pass splitting).
* **Person 4 (เอกศรัญ)**: Statistical Research & Visualizations (Hypothesis testing, Q1–Q3 mathematical analyses).
