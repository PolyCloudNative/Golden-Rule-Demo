from fastapi import FastAPI, Request, HTTPException, Response
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CONTENT_TYPE_LATEST
from starlette.responses import StreamingResponse
import time

app = FastAPI()

# Define Prometheus metrics
http_requests_total = Counter(
    "http_requests_total",
    "Total number of HTTP requests",
    ["method", "endpoint", "http_status"]
)
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"]
)
http_request_size_bytes = Histogram(
    "http_request_size_bytes",
    "HTTP request size in bytes",
    ["method", "endpoint"]
)
http_response_size_bytes = Histogram(
    "http_response_size_bytes",
    "HTTP response size in bytes",
    ["method", "endpoint"]
)
active_requests = Gauge(
    "active_requests",
    "Number of active requests"
)
error_counter = Counter(
    "error_counter",
    "Total number of HTTP errors",
    ["method", "endpoint", "http_status"]
)

@app.middleware("http")
async def record_request_start_time(request: Request, call_next):
    request.state.start_time = time.time()
    response = await call_next(request)
    return response

@app.middleware("http")
async def record_request_end_time(request: Request, call_next):
    response = await call_next(request)
    latency = time.time() - request.state.start_time
    http_request_duration_seconds.labels(
        request.method, request.url.path
    ).observe(latency)
    http_request_size_bytes.labels(
        request.method, request.url.path
    ).observe(request.headers.get("Content-Length", 0))
    if isinstance(response, StreamingResponse):
        response_size = 0
    else:
        response_size = len(response.content)
    http_response_size_bytes.labels(
        request.method, request.url.path
    ).observe(response_size)
    http_requests_total.labels(
        request.method, request.url.path, response.status_code
    ).inc()
    return response

@app.middleware("http")
async def increment_counter(request: Request, call_next):
    active_requests.inc()
    response = await call_next(request)
    active_requests.dec()
    return response

@app.middleware("http")
async def log_saturation(request: Request, call_next):
    max_concurrent_requests = 10  # set the maximum number of concurrent requests
    saturation_ratio = active_requests._value._value / max_concurrent_requests
    print(f"Saturation: {saturation_ratio}")
    return await call_next(request)

@app.middleware("http")
async def increment_error_counter(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except HTTPException as e:
        error_counter.labels(
            request.method, request.url.path, e.status_code
        ).inc()
        print(f"Incremented error counter for {request.method} {request.url.path} {e.status_code}")
        raise e


@app.get("/")
async def root():
    return {"message": "Hello, World!"}


@app.get("/generate_traffic")
async def generate_traffic():
    for i in range(100):
        response = await root()
        print(response)
    return {"message": "Generated traffic successfully."}


@app.get("/generate_error")
async def generate_error():
    raise HTTPException(status_code=500, detail="Generated an error.")


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
