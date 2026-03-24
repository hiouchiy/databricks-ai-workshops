# Workshop: Building & Deploying a Retail Grocery AI Agent on Databricks

This guide walks you through the **complete workshop** — from data generation to deploying the **Retail Grocery AI Agent** (a conversational agent with Genie, Vector Search, and long-term memory) both locally and as a Databricks App.

---

## Prerequisites

Before you begin, ensure you have:

- [ ] **Databricks CLI** installed and authenticated
  ```bash
  # Install (macOS)
  brew tap databricks/tap && brew install databricks

  # Authenticate
  databricks auth login --host https://<your-workspace>.cloud.databricks.com --profile DEFAULT

  # Verify
  databricks current-user me
  ```
- [ ] **uv** (Python package manager) installed — [install guide](https://docs.astral.sh/uv/getting-started/installation/)
- [ ] **Node.js 20+** installed (for the chat UI)
- [ ] **jq** installed (`brew install jq` on macOS)
- [ ] Access to a Databricks workspace with:
  - Serverless compute enabled
  - Foundation Model API (Claude) enabled
  - Unity Catalog enabled
  - Vector Search available
  - Lakebase available

---

## Phase 0: Clone the Repository

```bash
git clone https://github.com/AnanyaDBJ/databricks-ai-workshops.git
cd databricks-ai-workshops
```

The repo has two main directories:
- `data/` — Synthetic data generation scripts and policy documents
- `advanced/` — The AI agent application

---

## Phase 1: Data Preparation

This phase creates the structured datasets and policy document chunks that the agent queries.

### 1a. Create a Unity Catalog Schema

In your Databricks workspace (SQL Editor or notebook):

```sql
CREATE CATALOG IF NOT EXISTS <YOUR-CATALOG>;
CREATE SCHEMA IF NOT EXISTS <YOUR-CATALOG>.<YOUR-SCHEMA>;
```

### 1b. Find Your SQL Warehouse ID

```bash
databricks warehouses list
```

Note the `id` of an active SQL warehouse.

### 1c. Generate Structured Data (6 tables)

First, update the catalog and schema in the script:

```bash
cd data
```

Edit `execute_sql.py` — update lines 19-20:
```python
CATALOG = "<YOUR-CATALOG>"
SCHEMA = "<YOUR-SCHEMA>"
```

Then run:
```bash
python execute_sql.py --profile DEFAULT --warehouse-id <YOUR-WAREHOUSE-ID>
```

This creates 6 tables: `customers` (200 rows), `products` (500), `stores` (10), `transactions` (2000), `transaction_items` (8000+), `payment_history` (400).

### 1d. Generate Chunked Policy Documents

Edit `execute_chunking.py` — update lines 18-19:
```python
CATALOG = "<YOUR-CATALOG>"
SCHEMA = "<YOUR-SCHEMA>"
```

Then run:
```bash
python execute_chunking.py --profile DEFAULT --warehouse-id <YOUR-WAREHOUSE-ID>
```

This reads 7 policy markdown files from `policy_docs/`, chunks them (1000 chars, 200 overlap), and writes to `policy_docs_chunked` table.

### 1e. Create a Vector Search Endpoint

In the Databricks UI: **Compute** > **Vector Search** > **Create Endpoint**

- Name: `freshmart-policies` (or your preferred name)
- Wait for status: **READY** (5-10 minutes)

### 1f. Create a Vector Search Index

In Catalog Explorer, navigate to `<YOUR-CATALOG>.<YOUR-SCHEMA>.policy_docs_chunked`, then:

1. Click **Create** > **Vector Search Index**
2. Configure:
   - Index name: `policy_docs_index`
   - Primary key: `chunk_id`
   - Endpoint: select the endpoint from Step 1e
   - Embedding source column: `content`
   - Embedding model: `databricks-gte-large-en`
   - Sync mode: Triggered
3. Click **Create**

Note the full index path: `<YOUR-CATALOG>.<YOUR-SCHEMA>.policy_docs_index`

### 1g. Create a Genie Space

In the Databricks UI: **Genie** > **New Genie Space**

1. Name: `Retail Grocery Data`
2. Add all 6 structured tables from your schema
3. Select a SQL warehouse
4. Click **Create**
5. Copy the **Space ID** from the URL (e.g., `01ef...abcd`)

### 1h. Create a Lakebase Instance

```bash
databricks database create-database-instance <YOUR-INSTANCE-NAME> \
  --capacity=CU_1 \
  --enable-pg-native-login \
  --no-wait
```

Wait for it to be available:
```bash
databricks database get-database-instance <YOUR-INSTANCE-NAME> | jq '.state'
# Wait until "AVAILABLE"
```

### 1i. Create an MLflow Experiment

```bash
cd ../advanced

DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)

databricks experiments create \
  --name "/Users/$DATABRICKS_USERNAME/retail-grocery-ltm-memory"
```

Copy the returned `experiment_id` (a numeric string like `1159599...`).

### 1j. Register the System Prompt

```bash
cd ../advanced
uv run register-prompt --name <YOUR-CATALOG>.<YOUR-SCHEMA>.freshmart_system_prompt
```

This registers the FreshMart system prompt in Unity Catalog and sets a `@production` alias.

---

## Phase 2: Grant Individual User Permissions

Before local testing, your Databricks user needs permissions to access all resources.

### 2a. Lakebase — Create Your User Role

Connect to your Lakebase instance and create a role for your user:

```bash
databricks psql <YOUR-INSTANCE-NAME> -- -c "
CREATE ROLE \"your.email@company.com\" WITH LOGIN;
GRANT ALL ON DATABASE databricks_postgres TO \"your.email@company.com\";
"
```

Then grant schema and table permissions:

```bash
databricks psql <YOUR-INSTANCE-NAME> -- -d databricks_postgres -c "
GRANT ALL ON SCHEMA public TO \"your.email@company.com\";
GRANT ALL ON ALL TABLES IN SCHEMA public TO \"your.email@company.com\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO \"your.email@company.com\";
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO \"your.email@company.com\";
"
```

### 2b. Genie Space — Grant Access

In the Databricks UI: **Genie** > your space > **Share** > Add your user with **Can Run** permission.

### 2c. Vector Search — Grant Access

In Catalog Explorer: navigate to the index > **Permissions** > Add your user with **SELECT** permission.

### 2d. MLflow Experiment — Grant Access

In the Databricks UI: **Experiments** > your experiment > **Permissions** > Add your user with **Can Manage**.

### 2e. Unity Catalog — Grant Access

```sql
GRANT USE CATALOG ON CATALOG <YOUR-CATALOG> TO `your.email@company.com`;
GRANT USE SCHEMA ON SCHEMA <YOUR-CATALOG>.<YOUR-SCHEMA> TO `your.email@company.com`;
GRANT SELECT ON SCHEMA <YOUR-CATALOG>.<YOUR-SCHEMA> TO `your.email@company.com`;
```

---

## Phase 3: Local Development & Testing

### 3a. Set Up Environment Variables

```bash
cd advanced
cp .env.example .env
```

Edit `.env` and fill in your values:

```bash
DATABRICKS_CONFIG_PROFILE=DEFAULT
MLFLOW_EXPERIMENT_ID=<YOUR-EXPERIMENT-ID>
LAKEBASE_INSTANCE_NAME=<YOUR-INSTANCE-NAME>
GENIE_SPACE_ID=<YOUR-GENIE-SPACE-ID>
VECTOR_SEARCH_INDEX=<YOUR-CATALOG>.<YOUR-SCHEMA>.policy_docs_index
PROMPT_REGISTRY_NAME=<YOUR-CATALOG>.<YOUR-SCHEMA>.freshmart_system_prompt
```

For the Lakebase connection (needed by the chat UI):
```bash
PGHOST=<your-lakebase-hostname>
PGUSER=<your.email@company.com>
PGDATABASE=databricks_postgres
```

To find your Lakebase hostname:
```bash
databricks database get-database-instance <YOUR-INSTANCE-NAME> | jq -r '.read_write_dns'
```

### 3b. Start the App Locally

```bash
cd advanced
uv run start-app
```

This starts:
- **Backend** (FastAPI + MLflow AgentServer) on `http://localhost:8000`
- **Frontend** (React chat UI) on `http://localhost:3000`

### 3c. Test the Agent

Open `http://localhost:3000` in your browser and try:

- **Genie (structured data):** "What are the top 5 products by revenue?"
- **Vector Search (policy docs):** "What is the return policy for perishable items?"
- **Memory:** "Remember that I prefer organic products" → then in a new session: "What are my preferences?"

### 3d. Verify MLflow Traces

In the Databricks UI: **Experiments** > your experiment

- Verify traces are being logged for each request
- Check that traces follow OTEL format and show tool calls (Genie, Vector Search, memory)

### 3e. Test Conversation Memory

1. Create multiple chat sessions (use the "New Chat" button)
2. Verify conversation history is stored per-session
3. Check that long-term memory persists across sessions

---

## Phase 4: Configure for Databricks Apps Deployment

### 4a. Update `app.yaml` — Environment Variable Injection

Open `advanced/app.yaml`. The environment variables for Genie, Lakebase, and Vector Search use `valueFrom` to reference resources defined in `databricks.yml`. This means values are **injected automatically** at runtime.

Verify your `app.yaml` looks like this (no changes needed if it already does):

```yaml
  - name: MLFLOW_EXPERIMENT_ID
    valueFrom: experiment
  - name: LAKEBASE_INSTANCE_NAME
    valueFrom: lakebase_memory
  - name: GENIE_SPACE_ID
    valueFrom: retail_grocery_genie
  - name: VECTOR_SEARCH_INDEX
    valueFrom: policy_docs_index
```

> **How `valueFrom` works:** Each name (e.g., `lakebase_memory`) references a resource defined in `databricks.yml`. At deploy time, the platform resolves the resource and injects the appropriate value.

> **Note on Prompt Registry:** `PROMPT_REGISTRY_NAME` uses a static `value` in `databricks.yml` (not `value_from`) because MLflow Prompt Registry prompts are accessed via the MLflow API, not as UC securables.

### 4b. Update `databricks.yml` — Resource Definitions

Open `advanced/databricks.yml`. This file defines the Databricks Asset Bundle — the app, its environment, and the resources it needs.

#### Environment variables section

In the `config.env` section, verify the resource-backed variables use `value_from`, and the prompt registry uses a static `value`:

```yaml
        env:
          # ... static env vars above ...
          - name: MLFLOW_EXPERIMENT_ID
            value_from: "experiment"
          - name: LAKEBASE_INSTANCE_NAME
            value_from: "lakebase_memory"
          - name: GENIE_SPACE_ID
            value_from: "retail_grocery_genie"
          - name: VECTOR_SEARCH_INDEX
            value_from: "policy_docs_index"
          # Prompt Registry uses static value (not a UC securable resource)
          - name: PROMPT_REGISTRY_NAME
            value: "<YOUR-CATALOG>.<YOUR-SCHEMA>.freshmart_system_prompt"
```

> **Note:** `databricks.yml` uses `value_from` (underscore). `app.yaml` uses `valueFrom` (camelCase). Both are correct — they're different file formats.

#### Resource definitions

Replace the placeholder values with your actual resource IDs:

**MLflow Experiment:**
```yaml
        - name: "experiment"
          experiment:
            experiment_id: "<YOUR-EXPERIMENT-ID>"
            permission: "CAN_MANAGE"
```

**Genie Space:**
```yaml
        - name: "retail_grocery_genie"
          genie_space:
            name: "Retail Grocery Data"
            space_id: "<YOUR-GENIE-SPACE-ID>"
            permission: "CAN_RUN"
```

**Lakebase:**
```yaml
        - name: "lakebase_memory"
          database:
            instance_name: "<YOUR-LAKEBASE-INSTANCE-NAME>"
            database_name: "databricks_postgres"
            permission: "CAN_CONNECT_AND_CREATE"
```

**Vector Search Index:**
```yaml
        - name: "policy_docs_index"
          uc_securable:
            securable_full_name: "<YOUR-CATALOG>.<YOUR-SCHEMA>.policy_docs_index"
            securable_type: "TABLE"
            permission: "SELECT"
```

> **Important:** The `securable_full_name` uses **dots** (e.g., `my_catalog.my_schema.policy_docs_index`), not slashes.

---

## Phase 5: Deploy to Databricks Apps

### 5a. Validate the Bundle

```bash
cd advanced
databricks bundle validate -t dev
```

If you see errors, fix them before proceeding. Common issues:
- Mismatched resource names between `value_from` and the resource `name` fields
- Invalid experiment ID format
- Missing Databricks CLI authentication

### 5b. Deploy the Bundle

```bash
databricks bundle deploy -t dev
```

This command will:
1. Create the app `retail-grocery-ltm-memory` in your workspace
2. Upload all source code
3. Bind the resources (experiment, Genie space, Lakebase, Vector Search index)
4. Configure the environment variables via `valueFrom`

### 5c. Deploy Source Code to the App

```bash
DATABRICKS_USERNAME=$(databricks current-user me | jq -r .userName)
databricks apps deploy retail-grocery-ltm-memory \
  --source-code-path /Workspace/Users/$DATABRICKS_USERNAME/.bundle/retail_grocery_ltm_memory/dev/files
```

### 5d. Grant Lakebase Permissions to the App Service Principal

After deployment, the app gets assigned a **service principal**. This SP needs database permissions to create the memory tables.

```bash
# Get the app's service principal client ID
SP_CLIENT_ID=$(databricks apps get retail-grocery-ltm-memory --output json | jq -r '.service_principal_client_id')
echo "Service Principal Client ID: $SP_CLIENT_ID"

# Grant permissions for short-term memory (conversation state)
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-short-term \
  --instance-name <YOUR-LAKEBASE-INSTANCE-NAME>

# Grant permissions for long-term memory (user preferences, task history)
uv run python scripts/grant_lakebase_permissions.py "$SP_CLIENT_ID" \
  --memory-type langgraph-long-term \
  --instance-name <YOUR-LAKEBASE-INSTANCE-NAME>
```

Also grant the SP access to the Genie Space:

In the Databricks UI: **Genie** > your space > **Share** > Add the app's service principal with **Can Run** permission.

### 5e. Verify App Resources in the UI

In the Databricks UI: **Apps** > **retail-grocery-ltm-memory** > **Resources**

Verify all resources are bound:
- Experiment (CAN_MANAGE)
- Genie Space (CAN_RUN)
- Lakebase database (CAN_CONNECT_AND_CREATE)
- Vector Search index (SELECT)

### 5f. Start the App

```bash
databricks apps start retail-grocery-ltm-memory
```

Wait for the app to reach `RUNNING` state:

```bash
databricks apps get retail-grocery-ltm-memory
```

---

## Phase 6: Verify the Deployment

### Get the app URL

```bash
APP_URL=$(databricks apps get retail-grocery-ltm-memory --output json | jq -r '.url')
echo "App URL: $APP_URL"
```

### Test the agent API

```bash
# Get an OAuth token
TOKEN=$(databricks auth token | jq -r .access_token)

# Send a test message
curl -X POST "${APP_URL}/invocations" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"input": [{"role": "user", "content": "What stores do you have?"}]}'
```

### Open the Chat UI

Navigate to the app URL in your browser. You should see the chat interface.

Try the same test prompts as local testing:
- **Genie (structured data):** "What are the top 5 products by revenue?"
- **Vector Search (policy docs):** "What is the return policy for perishable items?"
- **Memory:** "Remember that I prefer organic products" → then in a new conversation: "What are my preferences?"

Verify MLflow traces are logged in the experiment UI, same as during local testing.

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| App stuck in `STOPPED` state | Run `databricks apps start retail-grocery-ltm-memory` |
| `302` error when calling the API | Use an OAuth token (`databricks auth token`), not a PAT |
| Permission denied on Lakebase | Re-run Phase 5d with the correct SP client ID. For local: re-run Phase 2a |
| `bundle validate` fails | Check that all `value_from` names match the resource `name` fields exactly |
| Vector Search returns empty results | Verify the index exists and has data in Catalog Explorer |
| App logs show missing env vars | Check `app.yaml` `valueFrom` names match `databricks.yml` resource names |
| App won't start after bundle deploy | Run the `databricks apps deploy` command from Phase 5c to deploy source code |
| Local app fails with Lakebase error | Check PGHOST, PGUSER in `.env` and verify your user role exists (Phase 2a) |
| Genie returns permission error | Grant access to your user (Phase 2b) or SP (Phase 5d) |

### Viewing App Logs

In the Databricks UI: **Apps** > **retail-grocery-ltm-memory** > **Logs**

Or via CLI:

```bash
databricks apps get-logs retail-grocery-ltm-memory
```

---

## Reference: How `valueFrom` Maps to Resources

```
app.yaml (valueFrom)          databricks.yml (resource name)       Injected Value
─────────────────────          ──────────────────────────────       ──────────────
experiment              ───►   experiment                     ───► experiment ID
lakebase_memory         ───►   lakebase_memory (database)     ───► Lakebase hostname
retail_grocery_genie    ───►   retail_grocery_genie           ───► Genie space ID
policy_docs_index       ───►   policy_docs_index              ───► securable_full_name (dot format)
```

> **Note:** `PROMPT_REGISTRY_NAME` is a static `value` in `databricks.yml`, not a `value_from` resource. MLflow Prompt Registry prompts are loaded via the MLflow API at runtime, not through UC securable resource binding.
