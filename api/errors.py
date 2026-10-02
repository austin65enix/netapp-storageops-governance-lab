from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class ServiceError(Exception):
    status_code: int
    code: str
    message: str

    def __str__(self) -> str:
        return self.message


async def service_error_handler(
    request: Request,
    exc: ServiceError,
) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "path": request.url.path,
            }
        },
    )


def ontap_timeout_error(
    operation_name: str,
) -> ServiceError:
    return ServiceError(
        status_code=504,
        code="ONTAP_TIMEOUT",
        message=(
            "ONTAP request timed out while performing "
            f"{operation_name}."
        ),
    )


def ontap_unavailable_error(
    operation_name: str,
) -> ServiceError:
    return ServiceError(
        status_code=502,
        code="ONTAP_UNAVAILABLE",
        message=(
            "Unable to retrieve "
            f"{operation_name} from the ONTAP source."
        ),
    )


def ontap_invalid_response_error(
    operation_name: str,
) -> ServiceError:
    return ServiceError(
        status_code=502,
        code="ONTAP_INVALID_RESPONSE",
        message=(
            "The ONTAP source returned invalid data while "
            f"processing {operation_name}."
        ),
    )
