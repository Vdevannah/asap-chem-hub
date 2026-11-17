# ASAP Chem Hub on AWS — deployment plan

Status: **plan only.** No AWS resource has been created, changed or deleted, and no `terraform apply` has
been run. Every step marked *(AWS)* below needs your approval first.

> **Region: us-east-2 (Ohio).** This account was created with AWS's new sign-up as a *project*.
> Its managed SCP (see [SCPs for projects](https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html))
> allows regional services only in the project's home region, us-east-2. In us-east-1 it denies
> everything except global ("partitional") services: `acm:*`, `cloudfront:*`, `route53:*`,
> `budgets:*` and others. The first `terraform plan` in us-east-1 failed on exactly that.
>
> Checked 2026-11-16 with read-only calls:
> - **us-east-2:** EC2, RDS, Lambda, ECS, ECR, Scheduler, SSM, Secrets Manager, Logs, S3 and IAM are
>   allowed. The Lambda concurrency limit is 400.
> - **us-east-1:** CloudFront and ACM are allowed.
>
> **What follows from that:**
> - **The stack runs in us-east-2.** CloudFront is global. The RDS CA bundle (`global-bundle.pem`)
>   covers every region.
> - **Custom domain (later): the ACM certificate must be in us-east-1**, because CloudFront only uses
>   certificates from there. The SCP allows ACM in us-east-1 (`acm:*` is exempt), so request the
>   certificate there, by hand or with the `aws.us_east_1` provider alias already in
>   `infra/versions.tf`. Route 53 is global and allowed.
> - **Spend limit warning.** If you ever set a *spend limit* in AWS Settings (your $25 budget is only
>   alerts, not a limit), AWS adds extra SCPs as the project nears it. These deny
>   `lambda:InvokeFunction` and `lambda:InvokeFunctionUrl`, so **the site's API would stop answering**.
>   They also deny creating Lambda functions, NAT gateways and ECS services. Keep any spend limit
>   well above the expected ≈ $16 a month.
> - **IAM is fine.** The project SCP protects only roles under `role/managed/*`; the roles here live
>   under `/` and are unaffected.
>
> **Decisions taken (2026-11-16):**
> - `*.cloudfront.net` address now; custom domain later via variables;
> - no budget in Terraform (it exists in the console);
> - RDS IAM authentication for the API and the jobs;
> - `/api/docs` off in production;
> - API responses cached 60 s, keyed on the whole query string;
> - Python 3.14 (newest generally available Lambda runtime; 3.15 is preview only).
>
> **How the Terraform differs from the step order in section 4:** everything is a single apply, with
> the schedules created disabled (`schedules_enabled = false`) until the migration is verified. The
> Lambda can exist before the data is loaded. The SSM loader is `scripts/put_ssm_params.py` (boto3),
> not a shell script. The budget (resource 20 in section 2) is not created by Terraform.

Region `us-east-2` (Ohio; the project account's home region). CloudFront is global. Everything is Terraform in `infra/`, and every taggable resource gets
`Project = asap-chem-hub` through the provider's `default_tags`.

---

## 1. Architecture

```
                         ┌──────────────────────────── CloudFront (one domain, HTTPS) ───────────────────────────┐
  browser ──────────────▶│  /*      → S3 site bucket (private, Origin Access Control)                            │
                         │  /api/*  → Lambda Function URL (AuthType AWS_IAM, Origin Access Control)               │
                         └───────────────────────────────────────────────┬───────────────────────────────────────┘
                                                                         │
                  default VPC ───────────────────────────────────────────┼──────────────────────────────────────
                  │                                                      ▼                                     │
                  │   Lambda "api" (FastAPI + Mangum, arm64)  ──3306──▶  RDS MySQL 8.4 (db.t4g.micro,          │
                  │   ENIs in 2 default subnets, sg-api                  single-AZ, private, sg-db)            │
                  │                                                      ▲                                     │
                  │   ECS Fargate task "jobs" (0.25 vCPU / 0.5 GB) ─3306─┘                                     │
                  │   public subnet + public IP, sg-jobs ──443──▶ RSS / Crossref / Springer / EPO / AWS APIs  │
                  └────────────────────────────────────────────────────────────────────────────────────────────┘
  EventBridge Scheduler ──RunTask──▶ jobs: articles+figures hourly · patents daily · cleanup daily
  SSM Parameter Store (SecureString): EPO / Springer keys, CROSSREF_MAILTO   ·   CloudWatch Logs (14 days)
```

### Key decisions

1. **No database password in AWS for the app: RDS IAM authentication.**
   A Lambda in the VPC has no route to the internet or to AWS APIs (no NAT, no VPC endpoints). It
   therefore cannot read SSM or Secrets Manager at runtime. The two ways around that both cost money:
   a NAT gateway is about $33/month, and SSM plus KMS interface endpoints are about $7/month each per
   AZ. With IAM database authentication, the Lambda creates a 15-minute token **locally**: it is a
   signature made from the function's role, with no network call. MySQL accepts that token over TLS.
   - **DB users.** `asap_api` is the API user and is SELECT-only. `asap_jobs` is the ingestion user,
     with SELECT, INSERT, UPDATE and DELETE on `asap_chem_hub`. Both use `AWSAuthenticationPlugin`.
   - **Master password.** RDS manages it in Secrets Manager (`manage_master_user_password = true`). It
     never appears in Terraform, in state or in code. It is used only by the one-off migration and
     admin tasks.
   - **Your local `.env` DB password** stays local. It isn't needed in AWS, so it isn't copied to SSM.
     If you'd rather have the jobs log in with a password, they *can* read one from SSM, because Fargate
     has a public IP. The API still couldn't without an endpoint.
2. **SecureStrings are created outside Terraform.** `scripts/put_ssm_params.sh` reads `.env` and
   writes `/asap-chem-hub/EPO_KEY`, `EPO_SECRET`, `SPRINGER_META_KEY`, `SPRINGER_OA_KEY` and
   `CROSSREF_MAILTO` as SecureString (AWS-managed `aws/ssm` key). It never prints a value. Terraform
   refers to the parameters by name/ARN only. Terraform stores the values of any resource it manages in
   its state, so it must not create them. The ECS task definition injects them as environment
   variables at container start (`secrets` → `valueFrom`).
3. **Lambda Function URL with `AuthType = AWS_IAM` behind CloudFront Origin Access Control (OAC).**
   Only CloudFront can call it; the bare function URL returns 403. The API is GET-only, so OAC's
   payload-signing limits for POST/PUT don't matter. The resource policy grants
   `cloudfront.amazonaws.com` both `lambda:InvokeFunctionUrl` and `lambda:InvokeFunction`, limited to
   this distribution's ARN.
4. **The `/api` prefix is stripped by Mangum** (`api_gateway_base_path="/api"`). FastAPI routes stay
   as they are (`/articles`, `/topics` …), so local development is unchanged.
5. **Reserved concurrency 10 on the Lambda.** A db.t4g.micro allows about 80 connections. Each request
   opens and closes one connection (current `api/db.py` behaviour), so a burst can't exhaust MySQL.
   Without RDS Proxy (which costs money even when idle), this is the guard.
6. **CloudFront caches `/api/*` for 60 seconds**, keyed on the full query string, which takes most of
   the load off Lambda and RDS. Static assets get long caching (file names are hashed); `index.html`
   gets a short TTL.
7. **Arm64 (Graviton) everywhere:** Lambda, Fargate and RDS t4g. It is about 20% cheaper.

### Security groups

| Group | Inbound | Outbound |
|---|---|---|
| `sg-db` (RDS) | TCP 3306 from `sg-api` and `sg-jobs` only | none |
| `sg-api` (Lambda) | none | TCP 3306 to `sg-db` |
| `sg-jobs` (Fargate) | none | TCP 443 and 80 to `0.0.0.0/0` (feeds, Crossref, Springer, EPO, ECR, SSM, Logs, S3); TCP 3306 to `sg-db` |

RDS: `publicly_accessible = false`. It does sit in the default VPC's subnets, which are public, but it
gets no public IP and only these two groups can reach it.

---

## 2. Resources to be created

**Bootstrap** (`infra/bootstrap/`, local state, applied once):
- S3 bucket `asap-chem-hub-tfstate-<account>`: versioning on, SSE-S3, all public access blocked.
  The main config uses it as its backend with `use_lockfile = true` (S3-native locking, no DynamoDB).

**Main** (`infra/`):

| # | Resource | Settings |
|---|---|---|
| 1 | `aws_security_group` × 3 + rules | as above |
| 2 | `aws_db_subnet_group` | 2+ default subnets in different AZs |
| 3 | `aws_db_parameter_group` (mysql8.4) | `require_secure_transport=1`, `character_set_server=utf8mb4`, `collation_server=utf8mb4_unicode_ci` (same as local) |
| 4 | `aws_db_instance` | MySQL 8.4, db.t4g.micro, single-AZ, 20 GB gp2 (free tier storage type; gp3 after upgrading if wanted), storage autoscaling off, encrypted, `publicly_accessible=false`, `iam_database_authentication_enabled=true`, `manage_master_user_password=true`, backups 1 day (Free plan limit, observed: 7 rejected, 1 accepted, not from AWS docs; raise to 7 after upgrading, no outage between non-zero values), `deletion_protection=true`, final snapshot on delete, Performance Insights off, Enhanced Monitoring off |
| 5 | Secrets Manager secret (created **by RDS**) | master password; not in state |
| 6 | `aws_s3_bucket` site + public-access block + bucket policy | private; policy allows only this CloudFront distribution (OAC) |
| 7 | `aws_s3_bucket` artifacts + lifecycle | Lambda zip, one-off DB export (`migration/`, deleted after 3 days) |
| 8 | `aws_cloudfront_origin_access_control` × 2 | one for S3, one for Lambda |
| 9 | `aws_cloudfront_distribution` | S3 origin + Lambda URL origin; `/api/*` behaviour (GET/HEAD/OPTIONS, 60 s cache, `AllViewerExceptHostHeader`); managed security-headers policy; `PriceClass_100`; default `*.cloudfront.net` certificate |
| 10 | `aws_lambda_function` "api" + `aws_lambda_function_url` + `aws_lambda_permission` × 2 | arm64; newest Lambda Python runtime that the dependencies support; 512 MB; 15 s timeout; VPC config; reserved concurrency 10 |
| 11 | `aws_iam_role` api | basic execution + VPC access + `rds-db:connect` for `asap_api` only |
| 12 | `aws_ecr_repository` "jobs" + lifecycle policy | scan on push; keep the last 5 images |
| 13 | `aws_ecs_cluster` | Container Insights **off** |
| 14 | `aws_ecs_task_definition` "jobs" | Fargate, ARM64, 256 CPU / 512 MB, awslogs, `secrets` from SSM |
| 15 | `aws_ecs_task_definition` "admin" | same image; adds the master secret; used only for migration and schema changes |
| 16 | `aws_iam_role` × 3 for ECS | execution role (ECR pull, Logs, `ssm:GetParameters` on `/asap-chem-hub/*`, `kms:Decrypt` on `aws/ssm`; admin also `secretsmanager:GetSecretValue` on the master secret only); task role (`rds-db:connect` for `asap_jobs`; admin also `s3:GetObject` on `migration/`) |
| 17 | `aws_scheduler_schedule_group` + 3 × `aws_scheduler_schedule` | `articles` (articles, then figures) hourly at :05; `patents` daily 05:00 UTC; `cleanup` daily 05:30 UTC; target ECS RunTask, FARGATE, public subnets, `assignPublicIp=ENABLED`, `sg-jobs`; 1 retry; created **disabled** until the migration is verified |
| 18 | `aws_iam_role` scheduler | `ecs:RunTask` on the jobs task definition; `iam:PassRole` for its two roles |
| 19 | `aws_cloudwatch_log_group` × 2 | `/aws/lambda/asap-chem-hub-api` and `/ecs/asap-chem-hub-jobs`, 14-day retention (created before the function and tasks so AWS doesn't create them with no expiry) |
| 20 | `aws_budgets_budget` | monthly $20; email alerts at 80% actual and 100% forecast (**needs your alert email**) |
| — | SSM parameters × 5 | **created by `scripts/put_ssm_params.sh`, not by Terraform** |

Not created: NAT gateway, VPC endpoints, RDS Proxy, Multi-AZ, Route 53 or ACM (unless you want a custom
domain), WAF, API Gateway.

Some resources can't carry tags: security-group rules, bucket policies, Lambda permissions, OAC and
individual Scheduler schedules. The schedule group is tagged.

---

## 3. Monthly cost estimate (us-east-2 on-demand list prices, the same as us-east-1 for these services)

Treat these as estimates and confirm them in the AWS Pricing Calculator before apply. If the account
still has free-tier credit (new accounts since July 2025 get credits instead of the old 12-month free
tier), most of this is covered at first.

| Resource | Basis | $/month | Costs when idle? |
|---|---|---|---|
| **RDS db.t4g.micro**, single-AZ | $0.016/h × 730 h | **≈ 11.70** | **Yes**, runs 24/7 |
| **RDS gp2 storage** 20 GB | $0.115/GB-month | **≈ 2.30** | **Yes** |
| RDS automated backups (1 day, Free plan limit; 7 after upgrading) | free up to 20 GB (= DB size) | ≈ 0 | snapshots kept after deletion cost $0.095/GB-month |
| **Secrets Manager** (RDS master secret) | $0.40/secret | **0.40** | **Yes** |
| Fargate ARM 0.25 vCPU / 0.5 GB | ≈ $0.0099/h; ≈ 55 task-hours (720 hourly runs × ~4 min, 30 patent runs × ~10 min, 30 cleanups) | ≈ 0.55 | no |
| Public IPv4 for Fargate tasks | $0.005/h while a task runs (~55 h) | ≈ 0.30 | no |
| Lambda | well inside the 1M requests / 400k GB-s monthly free tier | ≈ 0 | no |
| Lambda Function URL | free | 0 | no |
| CloudFront | always-free 1 TB and 10M requests a month | ≈ 0 | no |
| S3 (site + artifacts + state) | < 1 GB | ≈ 0.05 | yes (pennies) |
| ECR | ~0.3 GB × 5 images max, $0.10/GB | ≈ 0.15 | yes (pennies) |
| CloudWatch Logs | < 1 GB ingested ($0.50/GB), 14-day storage | ≈ 0.30 | no |
| EventBridge Scheduler | 14M free invocations a month | 0 | no |
| SSM Parameter Store standard + `aws/ssm` KMS | standard parameters free; ~4k decrypts a month | ≈ 0 | no |
| AWS Budgets | first two budgets free | 0 | no |
| *Optional:* Route 53 hosted zone (custom domain) | $0.50/zone + queries | 0.50 | yes |

**Total ≈ $16 a month**, of which **≈ $14.40 is idle cost** (RDS instance, storage and secret). RDS is
the only thing worth optimising: stopping it pauses instance hours but RDS restarts it after 7 days.
Moving to Aurora Serverless v2 doesn't scale to zero cheaply either.

**Expensive switches to avoid** (each would cost money even when idle):

| Switch | Cost |
|---|---|
| NAT gateway | ≈ $33/month + $0.045/GB |
| Interface VPC endpoints | ≈ $7.30/month each per AZ |
| RDS Multi-AZ | doubles the instance cost |
| RDS Proxy | ≈ $22/month minimum |
| Performance Insights long retention, Enhanced Monitoring | extra per-month charges |
| ECS Container Insights | extra per-month charges |
| Public IPv4 on anything always on | $0.005/h each |
| Storage autoscaling | grows storage without warning |
| Old RDS snapshots | $0.095/GB-month each |
| Old ECR images | $0.10/GB-month (the lifecycle policy covers this) |

---

## 4. Step order

Steps marked *(AWS)* create or change resources and wait for your go-ahead.

1. **App changes, locally (section 5).** Test against the local Docker MySQL:
   - the API through `uvicorn` and through the Mangum handler with a sample Function URL event;
   - the jobs image built for arm64 and run locally against the local DB;
   - the web build with `VITE_API_URL=/api` behind a local proxy.
2. **Review `terraform plan`** for bootstrap and main. Plan files aren't committed (see section 6).
3. *(AWS)* **Bootstrap:** create the state bucket.
4. *(AWS)* **Run `scripts/put_ssm_params.sh`** to create the 5 SecureString parameters from `.env`.
   Nothing is printed.
5. *(AWS)* **`terraform apply`, stage 1:**
   - security groups, DB subnet group, parameter group and RDS (≈ 10–15 minutes);
   - ECR, both S3 buckets, log groups, IAM roles, ECS cluster and task definitions;
   - the three schedules, **disabled**, and the budget.
6. *(AWS)* **Build and push** the jobs image (linux/arm64) to ECR. Build the Lambda zip and upload it
   to the artifacts bucket.
7. **Data migration (section 7).**
8. *(AWS)* **`terraform apply`, stage 2:** Lambda, Function URL, OAC, CloudFront (≈ 5–15 minutes to
   deploy).
9. *(AWS)* **Upload the website:** `npm run build` with `VITE_API_URL=/api`, then
   `aws s3 sync web/dist s3://<site-bucket> --delete` and a CloudFront invalidation of `/index.html`.
10. **Smoke tests.** Pass if all of these hold:
    - `https://<dist>.cloudfront.net/api/health` and `/api/status` respond.
    - The site loads both tabs and the About page.
    - A "CO2" search count matches local.
    - The bare Function URL returns 403.
    - `nc`/`mysql` from the internet to the RDS endpoint fails.
11. *(AWS)* **Run each job once by hand** (ECS RunTask with the same command overrides as the
    schedules). Check CloudWatch logs and `ingestion_runs`.
12. *(AWS)* **Enable the three schedules.** Then disable the local hourly job (`launchctl unload
    ~/Library/LaunchAgents/com.asapchemhub.ingest.plist`) so both don't poll publishers and EPO.
    Keep the local database for a week as a fallback.
13. **Later:** add a CLAUDE.md "Deploy" section (redeploy commands), the optional custom domain, and an
    alarm on failed `ingestion_runs`.

**Rollback:** CloudFront and the Lambda can be destroyed and recreated freely. RDS has deletion
protection and takes a final snapshot. Removing it is a deliberate two-step change.

---

## 5. Code changes needed in the app

1. **One DB connection helper for the API and the jobs** (`db_connect.py`, used by `api/db.py` and
   `load_poc.connect()`):
   - `DB_AUTH=password` (default, local `.env`, unchanged) or `DB_AUTH=iam`.
   - IAM mode: `boto3.client("rds").generate_db_auth_token(host, port, user, region)`. This signs
     locally and makes no network call. Connect with `ssl={"ca": DB_SSL_CA}` and the token as the
     password. PyMySQL sends it with `mysql_clear_password` over TLS; to be verified in step 1.
   - The RDS CA bundle (`global-bundle.pem`, public) is downloaded at build time into the Lambda zip and
     the image, not committed.
   - `load_dotenv()` stays; it does nothing when there's no `.env`.
2. **`api/lambda_handler.py`:** `handler = Mangum(app, lifespan="off", api_gateway_base_path="/api")`.
   - `/docs` and `/openapi.json`: either set `root_path="/api"` when running on Lambda, or turn the
     docs off in production (`DOCS=off`). Your choice.
   - CORS: keep the localhost dev origins; production is same-origin, so it needs no CORS.
3. **Split requirements:**
   - `requirements-api.txt`: fastapi, pydantic, mangum, pymysql, boto3.
   - `requirements-jobs.txt`: feedparser, requests, pymysql, python-dotenv, boto3.
   - `uvicorn` stays dev-only.
   - Pin versions for both.
4. **Lambda build script (`infra/build_lambda.sh`):**
   - `pip install --platform manylinux2014_aarch64 --only-binary=:all: --python-version <runtime> -t build/`
     so pydantic-core's compiled part matches Lambda;
   - copy `api/`, `db_connect.py` and the CA bundle, then zip.
   - Local is Python 3.14; choose the Lambda runtime to match what's available and test with it.
5. **Web `src/api.js`:**
   - `const BASE = import.meta.env.VITE_API_URL ?? "/api"`
   - `new URL(BASE + path, window.location.origin)`. The current `new URL(BASE + path)` throws for a
     relative base.
   - Add `web/.env.production` with `VITE_API_URL=/api` (no secret). Local dev keeps
     `http://127.0.0.1:8000`, either through `.env.local` or a Vite `server.proxy` for `/api` that
     strips the prefix.
6. **Jobs image:**
   - **`Dockerfile.jobs`:** `python:<version>-slim` for linux/arm64, non-root user, only the
     pipeline modules (`ingest.py`, `poc_feeds.py`, `epo.py`, `springer.py`, `topics.py`,
     `load_poc.py`, `db_connect.py`, `retag_topics.py`, `scripts/`), plus the CA bundle.
   - **`jobs/run_job.sh <articles|patents|cleanup>`:** `articles` runs `ingest.py articles` then
     `ingest.py figures`, the same order as `scripts/run_articles.sh`, without the Docker and launchd
     parts. Output goes to stdout, which CloudWatch collects.
   - **`.dockerignore`:** `.env*`, `.venv`, `logs/`, `web/`, `infra/`, `*.csv`, `preview*.html`,
     `__pycache__`, `.git`.
7. **Migration scripts (section 7):** `scripts/export_db.py` (local) and `scripts/import_db.py`
   (admin task).
8. **`scripts/put_ssm_params.sh`:** reads only the five needed keys from `.env` and writes each with
   `aws ssm put-parameter --type SecureString --overwrite`, passing the value through a `600`-mode temp
   file (`--cli-input-json file://…`) so it doesn't show in `ps` output or shell history. It deletes
   the temp file and echoes only parameter names.
9. **Environment variable names stay the same** (`EPO_KEY`, `SPRINGER_META_KEY`, `CROSSREF_MAILTO`,
   `DB_HOST` …), so `epo.py`, `springer.py` and `ingest.py` need no changes.

---

## 6. What must not be deployed or committed

Already ignored, and staying out of the image, the Lambda zip and the site:

| Item | Why |
|---|---|
| `.env` | DB passwords, EPO and Springer keys, CROSSREF_MAILTO |
| `logs/` | ingest log, title/abstract preview CSVs with article data |
| `.venv/`, `__pycache__/`, `web/node_modules/`, `web/dist/` | dist is uploaded to S3, never committed |
| `poc_results.csv`, `preview*.html`, `epo_results.csv`, `topics_review.csv` | local PoC outputs |

To add to `.gitignore` as part of this work:

| Item | Why |
|---|---|
| `infra/.terraform/`, `*.tfstate`, `*.tfstate.*`, `crash.log` | state lives in S3 only |
| `*.tfplan`, `tfplan*` | saved plan files can contain resource values |
| `*.tfvars` | if one holds your budget email; commit a `terraform.tfvars.example` instead |
| `build/`, `*.zip` | Lambda build output |
| `exports/`, `*.sql.gz`, `*.jsonl.gz` | the DB export is real data; it's written outside the repo anyway and deleted after import |
| `web/.env.local` | already covered by `web/.gitignore` |

**Do commit:** `infra/.terraform.lock.hcl`, so provider versions are pinned.

Local-only files that must not be deployed:

| File | Why |
|---|---|
| `docker-compose.yml`, `scripts/run_articles.sh`, the launchd plist | local DB and scheduler only |
| `test_epo.py`, `test_springer.py`, `tune_topics.py`, `load_poc.py`'s CSV loader `main()` | developer tools |
| `schema.sql` seed `INSERT`s | not run against RDS; the migration copies the real tables instead |

Checked now: no tracked file contains a hard-coded key, password or real email address. `poc_feeds.py`
only has the `you@example.com` placeholder. There are uncommitted changes in the working tree from
earlier work, so deploy from a commit you've reviewed, not from the working tree.

---

## 7. Data migration (RDS never public)

You asked for a safe way to copy the data without making RDS public. Recommended: **export locally →
private S3 → one-off "admin" Fargate task inside the VPC → RDS.**

1. **Pause the local hourly job** (`launchctl unload …`) so the export doesn't change underneath.
2. **Export: `scripts/export_db.py`** reads the local DB and writes one gzipped JSON-lines file
   outside the repo (`~/asap-export/asap_chem_hub-<date>.jsonl.gz`, mode 600). It contains:
   - every table's `SHOW CREATE TABLE`, which includes `title_plain` and every index;
   - every row of `journals`, `articles`, `article_topics`, `article_topic_links`, `patents`,
     `patent_topics`, `patent_topic_links` and `ingestion_runs`, **minus generated columns**
     (`title_plain` is rebuilt by MySQL);
   - row counts and a checksum per table.
   - It's only a few MB. It avoids `mysqldump` client and authentication-plugin differences, and needs
     no extra tools in the image.
3. **Test the import locally first** into a throwaway `mysql:8.4` container, then compare counts and
   checksums.
4. *(AWS)* **Upload** to `s3://<artifacts>/migration/` (SSE, private, deleted by lifecycle after 3
   days).
5. *(AWS)* **Run the admin task once (`import_db.py`):**
   - logs in as master (password from Secrets Manager, injected by ECS) over TLS;
   - creates the database (utf8mb4 / utf8mb4_unicode_ci) and the tables in foreign-key order;
   - inserts rows in batches with their original IDs and sets `AUTO_INCREMENT`;
   - creates `asap_api` (SELECT) and `asap_jobs` (SELECT/INSERT/UPDATE/DELETE) with
     `AWSAuthenticationPlugin`;
   - compares counts and checksums with the export and fails loudly on any mismatch.
6. *(AWS)* **Delete the export object** and the local file once step 10 passes.
7. **Enable the schedules right after**, to keep the gap small. The first hourly run catches up:
   ACS through the 7-day Crossref backup, patents through the 28-day lookback.

Alternatives considered:
- **Temporary bastion + SSM port forwarding:** a t4g.nano, about $0.10 for an hour of use. It works,
  but it's another instance to remember to delete.
- **Refill everything by ingestion:** it would lose most of the 30 days of articles, because RSS
  windows are short.

---

## 8. Open decisions for you

1. **Custom domain** or the `*.cloudfront.net` address? A custom domain adds Route 53 ($0.50/month)
   and a free ACM certificate, which must be in us-east-1 (allowed by the project SCP), even though the stack is in us-east-2.
2. **Budget alert email** (kept in an uncommitted `.tfvars`) and amount (suggested $20).
3. **DB auth:** IAM authentication as recommended, or a password in SSM for the jobs?
4. **Public API docs** at `/api/docs`, or turned off in production?
5. **Cache time for `/api/*`** (suggested 60 s; the site shows data updated hourly).
6. **Lambda Python runtime version** (local is 3.14).
