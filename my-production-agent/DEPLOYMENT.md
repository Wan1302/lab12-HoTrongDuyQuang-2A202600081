# Deployment Information

## Public URL

https://agent-production-3983.up.railway.app

## Platform

Railway

## Service Architecture

- `agent`: FastAPI production agent deployed from this repository.
- `Redis`: Railway Redis database used for conversation history, rate limiting, and monthly cost tracking.

## Test Commands

Set local shell variables:

```bash
BASE_URL="https://agent-production-3983.up.railway.app"
API_KEY="secret"
```

### Health Check

```bash
curl "$BASE_URL/health"
```

Expected result includes:

```json
{
  "status": "ok",
  "checks": {
    "redis": "ok",
    "llm": "mock"
  }
}
```

Verified result:

```json
{
  "status": "ok",
  "version": "1.0.0",
  "environment": "production",
  "checks": {
    "redis": "ok",
    "llm": "mock"
  }
}
```

### Readiness Check

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

Verified result:

```json
{
  "ready": true,
  "storage": "redis"
}
```

### API Test With Authentication

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

Verified result:

```json
{
  "user_id": "user1",
  "question": "Hello",
  "answer": "This is a mock AI response. In production, replace it with a real LLM provider.",
  "model": "mock-llm",
  "usage": {
    "budget_remaining_usd": 9.999952,
    "rate_limit_remaining": 9
  }
}
```

### Metrics Check

```bash
curl "$BASE_URL/metrics" \
  -H "X-API-Key: $API_KEY"
```

Verified result:

```json
{
  "error_count": 0,
  "rate_limit_per_minute": 10,
  "monthly_budget_usd": 10.0,
  "storage": "redis"
}
```

### Rate Limit Check

```bash
for i in {1..12}; do
  curl -s -o /dev/null -w "%{http_code}\n" \
    -X POST "$BASE_URL/ask" \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"question": "rate test", "user_id": "rate-user"}'
done
```

Verified result:

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

## Environment Variables Set

- `PORT`: provided by Railway
- `REDIS_URL`: Railway Redis connection URL
- `AGENT_API_KEY`: API key used by protected endpoints
- `ENVIRONMENT`: deployment environment
- `RATE_LIMIT_PER_MINUTE`: `10`
- `MONTHLY_BUDGET_USD`: `10.0`
- `LLM_MODEL`: `mock-llm`

