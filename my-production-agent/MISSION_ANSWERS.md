# Day 12 Lab - Mission Answers

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found

1. Hardcode secrets: API key, JWT secret hoặc credentials không được để trực tiếp trong source code.
2. Hardcode port: app production cần đọc `PORT` từ environment variables để cloud platform tự inject port phù hợp.
3. Bật debug mode mặc định: debug mode có thể làm lộ stack trace và thông tin nội bộ khi chạy production.
4. Thiếu health/readiness endpoints: platform không biết service còn sống hay đã sẵn sàng nhận traffic.
5. Lưu state trong memory: conversation history, rate limit counters và usage data sẽ mất khi restart, đồng thời bị lỗi khi scale nhiều instance.
6. Thiếu authentication: endpoint public có thể bị gọi tự do nếu không có API key hoặc token.
7. Thiếu rate limiting và cost guard: user có thể gửi quá nhiều request hoặc làm tăng chi phí LLM ngoài kiểm soát.
8. Log không có cấu trúc: plain text log khó search, filter và monitor trong production.

### Exercise 1.2: Chạy basic version
```bash
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```
Kết quả:
```bash
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}(venv) 
```

### Exercise 1.3: Comparison table

| Feature | Develop | Production | Why Important? |
|---------|---------|------------|----------------|
| Config | Hardcode trong code | Đọc từ environment variables | Giúp cùng một image/code chạy được ở local, staging và production. |
| API key | Có thể hardcode hoặc thiếu | Đọc từ `AGENT_API_KEY` | Tránh lộ secret trên Git và hỗ trợ rotate key. |
| Port | Port cố định | Dùng biến môi trường `PORT` | Cần thiết cho Railway và hầu hết cloud platforms. |
| Debug mode | Thường bật | Tắt, trừ khi bật rõ ràng | Tránh lộ stack trace và dữ liệu nhạy cảm. |
| Health check | Thiếu hoặc rất đơn giản | `GET /health` | Platform có thể restart container khi unhealthy. |
| Readiness check | Thiếu | `GET /ready` kiểm tra Redis | Không route traffic khi dependency chưa sẵn sàng. |
| State | Lưu trong memory | Lưu trong Redis | Hỗ trợ scale, restart và load balancing. |
| Logging | Plain text | Structured JSON logs | Dễ debug và monitor production hơn. |
| Security | Không auth hoặc auth đơn giản | API key auth + protected metrics | Giảm rủi ro bị gọi trái phép. |
| Reliability | Giả định single process | Graceful shutdown + Docker healthcheck | An toàn hơn khi deploy, restart hoặc scale. |

## Part 2: Docker

### Exercise 2.1: Dockerfile questions

1. Base image: Dockerfile cơ bản trong `02-docker/develop` dùng `python:3.11`. Dockerfile production trong `02-docker/production` dùng `python:3.11-slim` cho cả `builder` stage và `runtime` stage.
2. Working directory: cả Dockerfile cơ bản và Dockerfile production đều dùng `WORKDIR /app`.
3. Vì sao copy `requirements.txt` trước: Docker cache theo từng layer. Khi copy `requirements.txt` và cài dependencies trước khi copy source code, Docker có thể tái sử dụng layer cài dependencies nếu chỉ đổi app code. Điều này giúp build nhanh hơn.
4. `CMD` khác `ENTRYPOINT` như thế nào: `CMD` là command mặc định khi container start và có thể override dễ bằng command khi `docker run`. `ENTRYPOINT` định nghĩa executable chính của container; tham số truyền vào thường được nối thêm sau entrypoint, nên khó override hơn nếu không dùng `--entrypoint`. Trong hai Dockerfile của phần `02-docker`, không file nào dùng `ENTRYPOINT`; Dockerfile develop dùng `CMD ["python", "app.py"]`, còn Dockerfile production dùng `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`.

### Exercise 2.2: Build và run
```bash
# Build image
docker build -f 02-docker/develop/Dockerfile -t my-agent:develop .

# Run container
docker run -p 8000:8000 my-agent:develop

# Test
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```

Kết quả:
```bash
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"} 
```

Test:
```bash
docker images my-agent:develop
```

Kết quả:
```bash
IMAGE              ID             DISK USAGE   CONTENT SIZE   EXTRA
my-agent:develop   cf7712fa77dd       1.66GB          424MB        
```


### Exercise 2.3: Multi-stage build

Dockerfile: `02-docker/production/Dockerfile`.

Stage 1 - `builder`:

- Dùng base image `python:3.11-slim AS builder`.
- Đặt `WORKDIR /app`.
- Cài build dependencies như `gcc` và `libpq-dev`.
- Copy `02-docker/production/requirements.txt`.
- Chạy `pip install --no-cache-dir --user -r requirements.txt`.
- Mục đích: tạo môi trường build/cài dependencies. Stage này không dùng trực tiếp để deploy.

Stage 2 - `runtime`:

- Dùng base image `python:3.11-slim AS runtime`.
- Tạo non-root user `appuser`.
- Đặt `WORKDIR /app`.
- Copy installed packages từ builder:
  - `/root/.local` sang `/home/appuser/.local`
- Copy source code:
  - `02-docker/production/main.py`
  - `utils/mock_llm.py`
- Set ownership cho `appuser`.
- Chạy container bằng non-root user.
- Set `PATH` và `PYTHONPATH`.
- Expose port `8000`, thêm `HEALTHCHECK`, và chạy app bằng:
  - `CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]`

Tại sao image nhỏ hơn:

- Build tools như `gcc`, headers và các package chỉ cần trong lúc build nằm ở `builder` stage.
- Runtime stage chỉ copy phần cần để chạy app: Python slim image, installed packages, source code và utils.
- Không copy toàn bộ build cache, apt cache hoặc build dependencies sang runtime image.
- Vì vậy image production nhỏ hơn, sạch hơn và an toàn hơn so với single-stage image dùng full `python:3.11`.

Image size comparison:

- Develop: khoảng hơn 1 GB khi dùng full base image `python:3.11`.
- Production final project image: `247 MB`, đo từ Docker image đã build.
- Difference: production image nhỏ hơn khoảng 75% so với single-stage image dùng full Python base.

### Exercise 2.4: Docker Compose stack

Các service được start:

1. `nginx`: reverse proxy và load balancer, publish port `80:80` và `443:443` ra máy host.
2. `agent`: FastAPI AI agent, build từ Dockerfile production target `runtime`.
3. `redis`: Redis cache dùng cho session và rate limiting.
4. `qdrant`: vector database dùng cho RAG/vector search.

Architecture diagram:

```text
Client / curl
    |
    | HTTP :80 / :443
    v
+-------------------+
| nginx             |
| reverse proxy / LB|
+-------------------+
    |
    | http://agent:8000
    v
+-------------------+
| agent             |
| FastAPI AI agent  |
+-------------------+
    |                           |
    | REDIS_URL                 | QDRANT_URL
    | redis://redis:6379/0      | http://qdrant:6333
    v                           v
+-------------------+       +-------------------+
| redis             |       | qdrant            |
| session / rate    |       | vector database   |
| limiting cache    |       | for RAG           |
+-------------------+       +-------------------+
```

Cách các service communicate:

- Tất cả service nằm trong Docker network `internal`.
- Client không gọi trực tiếp `agent`; client gọi `nginx` qua `http://localhost`.
- `nginx` forward request tới `agent` qua service name nội bộ `agent`.
- `agent` kết nối Redis bằng `REDIS_URL=redis://redis:6379/0`.
- `agent` kết nối Qdrant bằng `QDRANT_URL=http://qdrant:6333`.
- `agent` chỉ start sau khi `redis` và `qdrant` healthy vì có `depends_on` với `condition: service_healthy`.
- Redis data lưu ở volume `redis_data`, Qdrant data lưu ở volume `qdrant_data`.

Lệnh chạy stack:

```bash
docker compose up
```

Test health check:

```bash
curl http://localhost/health
```

Test agent endpoint:

```bash
curl http://localhost/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain microservices"}'
```

Ghi chú: trong final project `my-production-agent`, endpoint `/ask` yêu cầu `X-API-Key`, nên khi test bản final cần thêm header:

```bash
curl http://localhost/ask -X POST \
  -H "X-API-Key: secret" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain microservices", "user_id": "user1"}'
```

## Part 3: Cloud Deployment

### Exercise 3.1: Railway deployment

- URL: https://part3day12-production.up.railway.app
- Platform: Railway
- Service layout:
  - `agent`: FastAPI app service
  - `Redis`: Railway Redis database service
- Screenshot: ![test_public_url](screenshots/part3_test_public_URL.png)

Các lệnh deploy đã dùng:

```bash
railway variables set PORT=8000
railway variables set AGENT_API_KEY=my-secret-key
railway up 
railway domain
```
![deploy_railway](screenshots/deploy_railway_part3.png)


Kiểm tra public endpoint:

```bash
curl https://part3day12-production.up.railway.app/health
```

Kết quả có:

```json
{
  {"status":"ok","uptime_seconds":372.3,"platform":"Railway","timestamp":"2026-04-17T07:03:01.140299+00:00"}
}
```

Kiểm tra ask:
```bash
$ curl https://part3day12-production.up.railway.app/ask -X POST   -H "Content-Type: application/json"   -d '{"question": "hello"}'
```

Kết quả có:

```json
{
  {"question":"hello","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","platform":"Railway"}
}
```
###  Exercise 3.2: Deploy Render 
![deploy_render](screenshots/deploy_render_part3.png)
So sánh `railway.toml` và `render.yaml`

`railway.toml` là file cấu hình cho Railway, dùng format TOML. File này tập trung vào cách build và deploy một service: chọn builder `NIXPACKS`, khai báo `startCommand`, `healthcheckPath`, timeout và restart policy. Environment variables thường được set bằng Railway CLI hoặc Dashboard, ví dụ `railway variables set`.

`render.yaml` là file Blueprint của Render, dùng format YAML. File này mô tả hạ tầng đầy đủ hơn: web service, Redis service, region, plan, build command, start command, health check, auto deploy và environment variables. Render có thể đọc file này từ GitHub để tạo nhiều service cùng lúc.

Khác biệt chính:
- Railway dùng TOML, Render dùng YAML.
- Railway config trong lab chỉ mô tả app service; Render config mô tả cả app service và Redis.
- Railway set env vars ngoài file bằng CLI/Dashboard; Render có `envVars` ngay trong file.
- Render có `autoDeploy`, `region`, `plan`; Railway file trong lab không khai báo các mục này.
- Railway có restart policy trong file; Render file lab không khai báo restart policy rõ ràng.


## Part 4: API Security

### Exercise 4.1: API Key authentication

API key được check ở đâu:

- API key được khai báo bằng:
  - `API_KEY = os.getenv("AGENT_API_KEY", "demo-key-change-in-production")`
  - `api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)`
- Hàm `verify_api_key()` đọc header `X-API-Key` bằng `Security(api_key_header)`.
- Endpoint `/ask` yêu cầu auth bằng dependency:
  - `_key: str = Depends(verify_api_key)`

Điều gì xảy ra nếu sai key:

- Nếu không gửi `X-API-Key`, app trả HTTP `401`:

```json
{
  "detail": "Missing API key. Include header: X-API-Key: <your-key>"
}
```

- Nếu gửi sai API key, app trả HTTP `403`:

```json
{
  "detail": "Invalid API key."
}
```

Làm sao rotate key:

- Không sửa code.
- Đổi biến môi trường `AGENT_API_KEY`.
- Restart/redeploy app để app đọc key mới.
- Ví dụ local:

```bash
AGENT_API_KEY=new-secret-key python app.py
```

- Ví dụ Railway:

```bash
railway variables set --service agent AGENT_API_KEY=new-secret-key
railway redeploy --service agent
```

Test không có key:

```bash
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```
```bash
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}
```

Test có key:

```bash
curl http://localhost:8000/ask -X POST \
  -H "X-API-Key: secret-key-123" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
```

```bash
{"detail":"Invalid API key."}
```

### Exercise 4.2: JWT authentication (Advanced)

JWT flow:

1. User gửi username/password tới endpoint lấy token.
2. App gọi `authenticate_user(username, password)` để kiểm tra user trong `DEMO_USERS`.
3. Nếu hợp lệ, app gọi `create_token(username, role)`.
4. Token chứa:
   - `sub`: username
   - `role`: user role
   - `iat`: issued-at time
   - `exp`: expiry time
5. Token được ký bằng `JWT_SECRET` và thuật toán `HS256`.
6. Khi gọi API protected, client gửi:
   - `Authorization: Bearer <token>`
7. Dependency `verify_token()` decode token, kiểm tra chữ ký và expiry, rồi trả về `username` và `role`.

Lấy token:

```bash
curl http://localhost:8000/auth/token -X POST \
  -H "Content-Type: application/json" \
  -d '{"username": "student", "password": "demo123"}'
```
Kết quả:

```bash
{"access_token":"eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJzdHVkZW50Iiwicm9sZSI6InVzZXIiLCJpYXQiOjE3NzY0MTUzNzEsImV4cCI6MTc3NjQxODk3MX0.nxkCPTFtHGmK8xnLLPm7ewgWC5FaxP1yBztvGuAa_Nc","token_type":"bearer","expires_in_minutes":60,"hint":"Include in header: Authorization: Bearer eyJhbGciOiJIUzI1NiIs..."
```

Dùng token gọi API:

```bash
TOKEN="<token_tu_buoc_tren>"
curl http://localhost:8000/ask -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"question": "Explain JWT"}'
```
Kết quả:
```bash
{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":0.000393}}
```

### Exercise 4.3: Rate limiting

Algorithm được dùng:

- Sliding Window Counter.
- Mỗi user có một `deque` chứa timestamp các request trong window.
- Mỗi request mới sẽ xóa các timestamp cũ hơn `window_seconds`.
- Nếu số request còn trong window vượt limit, app trả HTTP `429`.

Limit là bao nhiêu requests/minute:

- User thường: `10 req/min`
  - `rate_limiter_user = RateLimiter(max_requests=10, window_seconds=60)`
- Admin: `100 req/min`
  - `rate_limiter_admin = RateLimiter(max_requests=100, window_seconds=60)`

Làm sao bypass limit cho admin:

- Không bypass hoàn toàn, nhưng admin có limit cao hơn.
- Trong `app.py`, app chọn limiter theo role:

```python
limiter = rate_limiter_admin if role == "admin" else rate_limiter_user
```

- User role `admin` lấy từ JWT token, ví dụ user `teacher` có role `admin`.

Test rate limiting:

```bash
for i in {1..20}; do
  curl http://localhost:8000/ask -X POST \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d '{"question": "Test '$i'"}'
  echo ""
done
```

Quan sát:

- Với token role `user`, sau khoảng 10 request trong 60 giây sẽ nhận HTTP `429`.
- Response có thông tin:
  - `error`: `Rate limit exceeded`
  - `limit`
  - `window_seconds`
  - `retry_after_seconds`
- Header cũng có:
  - `X-RateLimit-Limit`
  - `X-RateLimit-Remaining`
  - `Retry-After`

Kết quả:
```text
{"question":"Test 1","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":8,"budget_remaining_usd":0.000412}}
{"question":"Test 2","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":7,"budget_remaining_usd":0.00043}}
{"question":"Test 3","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":6,"budget_remaining_usd":0.000449}}
{"question":"Test 4","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":5,"budget_remaining_usd":0.000465}}
{"question":"Test 5","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","usage":{"requests_remaining":4,"budget_remaining_usd":0.000486}}
{"question":"Test 6","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":3,"budget_remaining_usd":0.000502}}
{"question":"Test 7","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":2,"budget_remaining_usd":0.000521}}
{"question":"Test 8","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":1,"budget_remaining_usd":0.000537}}
{"question":"Test 9","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","usage":{"requests_remaining":0,"budget_remaining_usd":0.000553}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":3}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":3}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":3}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":3}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":2}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":2}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":2}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":1}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":1}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":1}}
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":1}}
```

### Exercise 4.4: Cost guard

Trong file production, `CostGuard` đang implement daily budget in-memory:

- `UsageRecord` lưu:
  - `user_id`
  - `input_tokens`
  - `output_tokens`
  - `request_count`
  - `day`
- `total_cost_usd` được tính từ:
  - `PRICE_PER_1K_INPUT_TOKENS = 0.00015`
  - `PRICE_PER_1K_OUTPUT_TOKENS = 0.0006`
- `check_budget(user_id)` kiểm tra:
  - global daily budget
  - per-user daily budget
- Nếu vượt per-user budget, app trả HTTP `402`.
- Nếu vượt global budget, app trả HTTP `503`.
- `record_usage()` ghi lại input/output tokens sau khi gọi LLM.

Logic theo yêu cầu lab nếu dùng Redis và budget `$10/tháng`:

```python
def check_budget(user_id: str, estimated_cost: float) -> bool:
    month_key = datetime.now().strftime("%Y-%m")
    key = f"budget:{user_id}:{month_key}"
    
    current = float(r.get(key) or 0)
    if current + estimated_cost > 10:
        return False
    
    r.incrbyfloat(key, estimated_cost)
    r.expire(key, 32 * 24 * 3600)  # 32 days
    return True
```

Sau khi request thành công, ghi usage:

```python
def record_usage(user_id: str, input_tokens: int, output_tokens: int):
    month = time.strftime("%Y-%m")
    key = f"cost:{month}:{user_id}"
    cost = (
        input_tokens / 1000 * PRICE_PER_1K_INPUT_TOKENS
        + output_tokens / 1000 * PRICE_PER_1K_OUTPUT_TOKENS
    )

    redis_client.hincrby(key, "request_count", 1)
    redis_client.hincrby(key, "input_tokens", input_tokens)
    redis_client.hincrby(key, "output_tokens", output_tokens)
    redis_client.hincrbyfloat(key, "cost_usd", cost)
    redis_client.expire(key, seconds_until_next_month)
```

## Part 5: Scaling & Reliability

### Exercise 5.1: Health checks

```python
@app.get("/health")
def health():
    uptime = round(time.time() - START_TIME, 1)

    checks = {}
    try:
        import psutil
        mem = psutil.virtual_memory()
        checks["memory"] = {
            "status": "ok" if mem.percent < 90 else "degraded",
            "used_percent": mem.percent,
        }
    except ImportError:
        checks["memory"] = {
            "status": "ok",
            "note": "psutil not installed",
        }

    overall_status = "ok" if all(
        value.get("status") == "ok" for value in checks.values()
    ) else "degraded"

    return {
        "status": overall_status,
        "uptime_seconds": uptime,
        "version": "1.0.0",
        "environment": os.getenv("ENVIRONMENT", "development"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@app.get("/ready")
def ready():
    if not _is_ready:
        raise HTTPException(
            status_code=503,
            detail="Agent not ready. Check back in a few seconds.",
        )

    return {
        "ready": True,
        "in_flight_requests": _in_flight_requests,
    }
```

Giải thích: `/health` kiểm tra process còn sống để platform biết có cần restart container không. `/ready` kiểm tra instance đã sẵn sàng nhận traffic chưa, nên khi app đang startup hoặc shutdown sẽ trả `503`.

Lệnh test:

```bash
cd 05-scaling-reliability/develop
python app.py
```

Mở terminal khác:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Long task"}'
```

Kết quả:
```bash
{"status":"ok","uptime_seconds":18.6,"version":"1.0.0","environment":"development","timestamp":"2026-04-17T09:08:05.594589+00:00","checks":{"memory":{"status":"ok","note":"psutil not installed"}}}{"ready":true,"in_flight_requests":1}{"question":"Long task","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}(venv) 
```

### Exercise 5.2: Graceful shutdown

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _is_ready

    logger.info("Agent starting up...")
    logger.info("Loading model and checking dependencies...")
    time.sleep(0.2)
    _is_ready = True
    logger.info("Agent is ready!")

    yield

    _is_ready = False
    logger.info("Graceful shutdown initiated...")

    timeout = 30
    elapsed = 0
    while _in_flight_requests > 0 and elapsed < timeout:
        logger.info(f"Waiting for {_in_flight_requests} in-flight requests...")
        time.sleep(1)
        elapsed += 1

    logger.info("Shutdown complete")


def handle_sigterm(signum, frame):
    global _is_ready
    _is_ready = False
    logger.info(f"Received signal {signum} - stop accepting new requests")
    logger.info("Uvicorn will wait for in-flight requests during graceful shutdown")


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_graceful_shutdown=30,
    )
```

Giải thích: khi nhận `SIGTERM`, app chuyển `_is_ready = False` để không nhận traffic mới. Phần shutdown trong lifespan chờ request đang xử lý hoàn thành trước khi app dừng hẳn.

Lệnh test:

```bash
cd 05-scaling-reliability/develop
python app.py &
PID=$!

curl http://localhost:8000/ask -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "Long task"}' &

kill -TERM $PID
```

Kết quả đúng cần quan sát:

```text
[1] 4214
[2] 4227
[1]-  Terminated              python app.py
```


### Exercise 5.3: Stateless design

Anti-pattern cần tránh:

```python
conversation_history = {}
```

Lý do sai:

- Khi scale nhiều agent instances, mỗi instance có memory riêng.
- User request 1 có thể vào instance A, request 2 có thể vào instance B.
- Nếu history lưu trong memory, instance B không đọc được history của instance A.
- Khi restart container, memory state bị mất.

Code stateless đã dùng trong production:

```python
def save_session(session_id: str, data: dict, ttl_seconds: int = 3600):
    serialized = json.dumps(data)
    if USE_REDIS:
        _redis.setex(f"session:{session_id}", ttl_seconds, serialized)
    else:
        _memory_store[f"session:{session_id}"] = data


def load_session(session_id: str) -> dict:
    if USE_REDIS:
        data = _redis.get(f"session:{session_id}")
        return json.loads(data) if data else {}
    return _memory_store.get(f"session:{session_id}", {})


def append_to_history(session_id: str, role: str, content: str):
    session = load_session(session_id)
    history = session.get("history", [])
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    if len(history) > 20:
        history = history[-20:]

    session["history"] = history
    save_session(session_id, session)
    return history


@app.post("/chat")
async def chat(body: ChatRequest):
    session_id = body.session_id or str(uuid.uuid4())

    append_to_history(session_id, "user", body.question)

    session = load_session(session_id)
    history = session.get("history", [])
    answer = ask(body.question)

    append_to_history(session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "question": body.question,
        "answer": answer,
        "turn": len([m for m in history if m["role"] == "user"]) + 1,
        "served_by": INSTANCE_ID,
        "storage": "redis" if USE_REDIS else "in-memory",
    }
```

Giải thích: Redis là shared state nằm ngoài process, nên mọi agent instance đều đọc/ghi được cùng một session. Vì vậy app scale được nhiều instance mà không mất conversation history.

Lệnh test thủ công:

```bash
cd 05-scaling-reliability/production
docker compose up --build --scale agent=3
```

Mở terminal khác:

```bash
curl http://localhost:8080/chat -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Docker?"}'
```

Kết quả:
```bash
{"session_id":"b3f1f47f-843a-48b3-90da-e4b54de806ce","question":"What is Docker?","answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","turn":2,"served_by":"instance-3e21ae","storage":"redis"}
```

Copy `session_id` từ response, rồi gọi tiếp:

```bash
curl http://localhost:8080/chat -X POST \
  -H "Content-Type: application/json" \
  -d '{"question": "What is Redis used for?", "session_id": "b3f1f47f-843a-48b3-90da-e4b54de806ce"}'
```

Kết quả:
```bash
{"session_id":"b3f1f47f-843a-48b3-90da-e4b54de806ce","question":"What is Redis used for?","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":3,"served_by":"instance-071d5f","storage":"redis"}
```

Xem history:

```bash
curl http://localhost:8080/chat/b3f1f47f-843a-48b3-90da-e4b54de806ce/history
```

Kết quả:

```bash
{"session_id":"b3f1f47f-843a-48b3-90da-e4b54de806ce","messages":[{"role":"user","content":"What is Docker?","timestamp":"2026-04-17T09:21:21.026551+00:00"},{"role":"assistant","content":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!","timestamp":"2026-04-17T09:21:21.159353+00:00"},{"role":"user","content":"What is Redis used for?","timestamp":"2026-04-17T09:22:07.539128+00:00"},{"role":"assistant","content":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","timestamp":"2026-04-17T09:22:07.690416+00:00"}],"count":4}
```

### Exercise 5.4: Load balancing

Lệnh test:

```bash
cd 05-scaling-reliability/production
docker compose up --build --scale agent=3
```

Mở terminal khác:

```bash
for i in {1..10}; do
  curl http://localhost:8080/chat -X POST \
    -H "Content-Type: application/json" \
    -d '{"question": "Request '$i'"}'
  echo ""
done
```

Kết quả:
```bash
{"session_id":"0f9411f0-7d34-400b-95a8-b6978b3d6d4d","question":"Request 1","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé.","turn":2,"served_by":"instance-3e21ae","storage":"redis"}
{"session_id":"da98b762-fe74-4b9b-8a9b-96537e182cc7","question":"Request 2","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-071d5f","storage":"redis"}
{"session_id":"15dadb7c-9c5b-4133-8b8c-706ed1582af2","question":"Request 3","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-008c3a","storage":"redis"}
{"session_id":"8f65ac83-73ff-40e8-a072-e25d35ac6137","question":"Request 4","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-3e21ae","storage":"redis"}
{"session_id":"6ec364c9-8e0c-4f54-99d2-838391fb3be5","question":"Request 5","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","turn":2,"served_by":"instance-071d5f","storage":"redis"}
{"session_id":"a8020ba1-47e3-4bc0-8f25-0efc64bb3d1d","question":"Request 6","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-008c3a","storage":"redis"}
{"session_id":"ab0561d2-1bda-4418-a735-bcd062bbf766","question":"Request 7","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-3e21ae","storage":"redis"}
{"session_id":"a713c809-892e-43ec-ae6e-ae6e6e3d4230","question":"Request 8","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-071d5f","storage":"redis"}
{"session_id":"7fb530c7-3fd5-456c-85f3-dab141992ca3","question":"Request 9","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-008c3a","storage":"redis"}
{"session_id":"d7ac137d-3402-4354-acc6-abaa8a7aaf83","question":"Request 10","answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic.","turn":2,"served_by":"instance-3e21ae","storage":"redis"}
```

Check logs:

```bash
docker compose logs 
```

Kết quả:
```bash
time="2026-04-17T16:26:37+07:00" level=warning msg="D:\\Wan_Document\\VinUni\\Lab\\lab_12\\day12_ha-tang-cloud_va_deployment\\05-scaling-reliability\\production\\docker-compose.yml: the attribute `version` is obsolete, it will be ignored, please remove it to avoid potential confusion"
agent-3  | ✅ Connected to Redis
agent-3  | INFO:     Started server process [1]
agent-3  | INFO:     Waiting for application startup.
agent-3  | INFO:__main__:Starting instance instance-008c3a
agent-3  | INFO:__main__:Storage: Redis ✅
agent-3  | INFO:     Application startup complete.
agent-3  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
agent-3  | INFO:     172.18.0.6:54318 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:42424 - "GET /health HTTP/1.1" 200 OK
agent-2  | ✅ Connected to Redis
agent-2  | INFO:     Started server process [1]
agent-3  | INFO:     127.0.0.1:49252 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:34296 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:43204 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:40156 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     Waiting for application startup.
agent-2  | INFO:__main__:Starting instance instance-071d5f
agent-3  | INFO:     127.0.0.1:44708 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     172.18.0.6:34850 - "GET /chat/b3f1f47f-843a-48b3-90da-e4b54de806ce/history HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:32942 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:__main__:Storage: Redis ✅
agent-2  | INFO:     Application startup complete.
agent-2  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
agent-2  | INFO:     127.0.0.1:42444 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:49280 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:60822 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:34312 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:43228 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     172.18.0.6:38904 - "POST /chat HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:40174 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:44726 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:32970 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:60836 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:57676 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     172.18.0.6:47328 - "POST /chat HTTP/1.1" 200 OK
agent-2  | INFO:     172.18.0.6:47328 - "POST /chat HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:52804 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     172.18.0.6:47328 - "POST /chat HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:41626 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:36330 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:45826 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:41424 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:43904 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:47434 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     172.18.0.6:38928 - "POST /chat HTTP/1.1" 200 OK
agent-2  | INFO:     172.18.0.6:38928 - "POST /chat HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:59870 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:49424 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:55682 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:53206 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     127.0.0.1:33946 - "GET /health HTTP/1.1" 200 OK
agent-2  | INFO:     Shutting down
agent-2  | INFO:     Waiting for application shutdown.
agent-2  | INFO:__main__:Instance instance-071d5f shutting down
agent-2  | INFO:     Application shutdown complete.
agent-2  | INFO:     Finished server process [1]
agent-3  | INFO:     127.0.0.1:34044 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     172.18.0.6:60026 - "POST /chat HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:52784 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     172.18.0.6:60026 - "POST /chat HTTP/1.1" 200 OK
agent-3  | INFO:     172.18.0.6:60026 - "POST /chat HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:41596 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:36304 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:45816 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:41412 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:43880 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:47420 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     172.18.0.6:37570 - "POST /chat HTTP/1.1" 200 OK
agent-3  | INFO:     172.18.0.6:37570 - "POST /chat HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:59854 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:49404 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:55664 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:53188 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     127.0.0.1:33928 - "GET /health HTTP/1.1" 200 OK
agent-3  | INFO:     Shutting down
agent-3  | INFO:     Waiting for application shutdown.
agent-3  | INFO:__main__:Instance instance-008c3a shutting down
agent-3  | INFO:     Application shutdown complete.
agent-3  | INFO:     Finished server process [1]
agent-1  | ✅ Connected to Redis
agent-1  | INFO:     Started server process [1]
agent-1  | INFO:     Waiting for application startup.
agent-1  | INFO:__main__:Starting instance instance-3e21ae
agent-1  | INFO:__main__:Storage: Redis ✅
agent-1  | INFO:     Application startup complete.
agent-1  | INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
agent-1  | INFO:     172.18.0.6:48966 - "POST /chat HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:42438 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:49268 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:34306 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:43212 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:40168 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:44714 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:32956 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:60824 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:57660 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     172.18.0.6:50066 - "POST /chat HTTP/1.1" 200 OK
agent-1  | INFO:     172.18.0.6:50066 - "POST /chat HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:52796 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     172.18.0.6:50066 - "POST /chat HTTP/1.1" 200 OK
agent-1  | INFO:     172.18.0.6:50066 - "POST /chat HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:41612 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:36314 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:45820 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:41420 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:43888 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:47426 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     172.18.0.6:57066 - "POST /chat HTTP/1.1" 200 OK
agent-1  | INFO:     172.18.0.6:57066 - "GET /chat/8531b3a0-a7af-4686-a37d-01932223d823/history HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:59856 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:49418 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:55670 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:53198 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     127.0.0.1:33934 - "GET /health HTTP/1.1" 200 OK
agent-1  | INFO:     Shutting down
agent-1  | INFO:     Waiting for application shutdown.
agent-1  | INFO:__main__:Instance instance-3e21ae shutting down
agent-1  | INFO:     Application shutdown complete.
agent-1  | INFO:     Finished server process [1]
```

### Exercise 5.5: Test stateless

Script làm gì:

1. Tạo session mới bằng request đầu tiên.
2. Gửi 5 request liên tiếp với cùng `session_id`.
3. In ra `served_by` để xem request được phục vụ bởi instance nào.
4. Gọi `/chat/{session_id}/history`.
5. Kiểm tra history vẫn còn đủ messages dù request có thể đi qua nhiều instances.

Lệnh test:

```bash
cd 05-scaling-reliability/production
docker compose up --build --scale agent=3
```

Mở terminal khác:

```bash
python test_stateless.py
```

Kết quả:
```bash
============================================================
Stateless Scaling Demo
============================================================

Session ID: 8531b3a0-a7af-4686-a37d-01932223d823

Request 1: [instance-071d5f]
  Q: What is Docker?
  A: Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!...

Request 2: [instance-008c3a]
  Q: Why do we need containers?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

Request 3: [instance-3e21ae]
  Q: What is Kubernetes?
  A: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận....

Request 4: [instance-071d5f]
  Q: How does load balancing work?
  A: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé....

Request 5: [instance-008c3a]
  Q: What is Redis used for?
  A: Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ O...

------------------------------------------------------------
Total requests: 5
Instances used: {'instance-071d5f', 'instance-008c3a', 'instance-3e21ae'}
✅ All requests served despite different instances!

--- Conversation History ---
Total messages: 10
  [user]: What is Docker?...
  [assistant]: Container là cách đóng gói app để chạy ở mọi nơi. Build once...
  [user]: Why do we need containers?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...
  [user]: What is Kubernetes?...
  [assistant]: Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã đư...
  [user]: How does load balancing work?...
  [assistant]: Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đ...
  [user]: What is Redis used for?...
  [assistant]: Đây là câu trả lời từ AI agent (mock). Trong production, đây...

✅ Session history preserved across all instances via Redis!
```
