from time import perf_counter

from fastapi import FastAPI, Request
from fastapi.responses import Response

from api.config import settings
from api.errors import (
    ServiceError,
    service_error_handler,
)
from api.metrics import (
    APP_VERSION,
    HTTP_DURATION,
    HTTP_REQUESTS,
    HTTP_RESPONSES,
    render_metrics,
)
from api.routes.evidence import (
    router as evidence_router,
)
from api.routes.inventory import (
    router as inventory_router,
)
from api.routes.operational import (
    router as operational_router,
)
from api.routes.storage import (
    router as storage_router,
)


app = FastAPI(
    title="Enyrax StorageOps API",
    description=(
        "Storage inventory, capacity, change "
        "detection and evidence service."
    ),
    version=APP_VERSION,
)


app.add_exception_handler(
    ServiceError,
    service_error_handler,
)


@app.middleware("http")
async def prometheus_http_metrics(
    request: Request,
    call_next,
):
    if request.url.path == "/metrics":
        return await call_next(request)

    started_at = perf_counter()
    response = None

    try:
        response = await call_next(request)
        return response

    finally:
        route = request.scope.get("route")

        endpoint = getattr(
            route,
            "path",
            "__unmatched__",
        )

        method = request.method

        status_code = (
            str(response.status_code)
            if response is not None
            else "500"
        )

        duration = perf_counter() - started_at

        HTTP_REQUESTS.labels(
            method=method,
            endpoint=endpoint,
        ).inc()

        HTTP_RESPONSES.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code,
        ).inc()

        HTTP_DURATION.labels(
            method=method,
            endpoint=endpoint,
        ).observe(duration)


app.include_router(storage_router)
app.include_router(inventory_router)
app.include_router(evidence_router)
app.include_router(operational_router)


@app.get("/")
def root():
    return {
        "service": "Enyrax StorageOps API",
        "version": APP_VERSION,
        "status": "running",
    }


@app.get("/healthz")
def healthz():
    return {
        "status": "ok",
        "source": settings.storage_source,
        "ontap_base_url": (
            settings.ontap_base_url
        ),
        "ontap_timeout_seconds": (
            settings.ontap_timeout_seconds
        ),
    }


@app.get(
    "/metrics",
    include_in_schema=False,
)
def metrics():
    payload, content_type = render_metrics()

    return Response(
        content=payload,
        media_type=content_type,
    )
