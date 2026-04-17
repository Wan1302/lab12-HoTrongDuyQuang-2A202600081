# My Production Agent

Production-ready AI agent for the Day 12 lab.

- REST API with `POST /ask`
- Conversation history in Redis
- API key authentication
- Redis-backed rate limiting, default `10 req/min/user`
- Redis-backed monthly cost guard, default `$10/user/month`
- Health and readiness probes
- Structured JSON logging
- Graceful shutdown through FastAPI lifespan and Uvicorn
- Multi-stage Dockerfile running as a non-root user
- Docker Compose stack with `nginx + agent + redis`
- Railway deployment config

## Requirements

Install these before running the project:

- Docker Desktop
- `curl`
- Railway CLI, only needed for deployment
- Python 3.11+, only needed for `check_production_ready.py`

## Structure

```text
my-production-agent/
|-- app/
|   |-- __init__.py
|   |-- main.py
|   |-- config.py
|   |-- auth.py
|   |-- rate_limiter.py
|   |-- cost_guard.py
|   `-- redis_client.py
|-- utils/
|   `-- mock_llm.py
|-- Dockerfile
|-- docker-compose.yml
|-- nginx.conf
|-- railway.toml
|-- .env.example
|-- .dockerignore
|-- check_production_ready.py
`-- requirements.txt
```

## Local Setup

From the repository root:

```bash
cd my-production-agent
```

If you are already inside the `my-production-agent` directory, skip this `cd` command.

Create a local `.env` file:

```bash
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

The default local API key is:

```text
dev-key-change-me
```

## Local Docker Run

Build the agent image:

```bash
docker compose build --no-cache agent
```

Run the full local stack with 3 agent replicas:

```bash
docker compose up --build --scale agent=3
```

The local Nginx load balancer listens on:

```text
http://localhost
```

If port `80` is already used on your machine, edit `docker-compose.yml`:

```yaml
ports:
  - "8080:80"
```

Then use:

```text
http://localhost:8080
```

Stop local containers:

```bash
docker compose down -v
```

## Local Test Commands

Health and readiness:

```bash
curl http://localhost/health
curl http://localhost/ready
```

If you changed the local port to `8080`, use:

```bash
curl http://localhost:8080/health
curl http://localhost:8080/ready
```

For the rest of the local test commands, also replace `http://localhost` with `http://localhost:8080` if you changed the port mapping.

Authentication must reject missing API key:

```bash
curl -i -X POST http://localhost/ask \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"Hello"}'
```

Expected status:

```text
401 Unauthorized
```

Authenticated request:

```bash
curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"What is Docker?"}'
```

Test conversation history. First, call `/ask` and copy the returned `session_id`:

```bash
curl -X POST http://localhost/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id":"student1","question":"My name is Alice"}'
```

Then inspect history:

```bash
curl http://localhost/history/student1/PASTE_SESSION_ID_HERE \
  -H "X-API-Key: dev-key-change-me"
```

Protected metrics endpoint:

```bash
curl http://localhost/metrics \
  -H "X-API-Key: dev-key-change-me"
```

Rate limit test. The first 10 requests should return `200`, then requests should return `429`.

```bash
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST http://localhost/ask \
    -H "X-API-Key: dev-key-change-me" \
    -H "Content-Type: application/json" \
    -d '{"question": "rate test", "user_id": "rate-user"}'
done
```

Expected result:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```

## Railway Deployment

Railway uses service variables, not the local `.env` file. Deploy the app code to an app service such as `agent`, and keep Redis as a separate Railway Redis database service.

Login and create or link a Railway project:

```bash
railway login
railway init
```

Select the app service that will run this code:

```bash
railway service
```

If the project does not have an app service yet, create one in the Railway dashboard, then run `railway service` again and select it.

Create a Redis database service in the Railway dashboard:

```text
Railway Dashboard -> Project -> New -> Database -> Redis
```

Set variables on the app service. If your app service is named `agent` and your Redis service is named `Redis`, run:

```bash
railway variables set --service agent ENVIRONMENT=production
railway variables set --service agent AGENT_API_KEY=your-api-key
railway variables set --service agent REDIS_URL='${{Redis.REDIS_URL}}'
railway variables set --service agent MONTHLY_BUDGET_USD=10.0
railway variables set --service agent RATE_LIMIT_PER_MINUTE=10
railway variables set --service agent LLM_MODEL=mock-llm
```

If the Redis service has a different name, replace `Redis` in the reference:

```bash
railway variables set --service agent REDIS_URL='${{YOUR_REDIS_SERVICE_NAME.REDIS_URL}}'
```

Deploy the app service:

```bash
railway up --service agent
```

Generate a public domain:

```bash
railway domain --service agent
```

After deployment, set your public URL and API key in shell variables:

```bash
BASE_URL="https://YOUR-APP.up.railway.app"
API_KEY="your-api-key"
```

## Railway Test Commands

Health check:

```bash
curl "$BASE_URL/health"
```

Expected result includes:

```json
{
  "status": "ok",
  "environment": "production",
  "checks": {
    "redis": "ok",
    "llm": "mock"
  }
}
```

Readiness check:

```bash
curl "$BASE_URL/ready"
```

Expected result:

```json
{
  "ready": true,
  "storage": "redis"
}
```

Authentication must reject missing API key:

```bash
curl -i -X POST "$BASE_URL/ask" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello", "user_id": "user1"}'
```

Expected status:

```text
401 Unauthorized
```

Authenticated agent request:

```bash
curl -X POST "$BASE_URL/ask" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello", "user_id": "user1"}'
```

Expected result includes:

```json
{
  "user_id": "user1",
  "question": "Hello",
  "model": "mock-llm",
  "usage": {
    "rate_limit_remaining": 9
  }
}
```

Protected metrics endpoint:

```bash
curl "$BASE_URL/metrics" \
  -H "X-API-Key: $API_KEY"
```

Expected result includes:

```json
{
  "error_count": 0,
  "rate_limit_per_minute": 10,
  "monthly_budget_usd": 10.0,
  "storage": "redis"
}
```

Rate limit test:

```bash
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST "$BASE_URL/ask" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"question": "rate test", "user_id": "rate-user"}'
done
```

Expected result:

```text
200
200
200
200
200
200
200
200
200
200
429
429
```

## Production Readiness

From the `my-production-agent` directory:

```bash
python check_production_ready.py
```

Expected result:

```text
20/20 checks passed (100%)
PRODUCTION READY
```
