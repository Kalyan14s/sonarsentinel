import pytest

from sonarsentinel import errors


@pytest.mark.parametrize(
    ("cls", "code", "status"),
    [
        (errors.ValidationError, "VALIDATION_ERROR", 400),
        (errors.NavCsvInvalidError, "NAV_CSV_INVALID", 400),
        (errors.NotFoundError, "NOT_FOUND", 404),
        (errors.JobNotCancellableError, "JOB_NOT_CANCELLABLE", 409),
        (errors.FileTooLargeError, "FILE_TOO_LARGE", 413),
        (errors.UnsupportedFormatError, "UNSUPPORTED_FORMAT", 415),
        (errors.CorruptHeaderError, "CORRUPT_HEADER", 422),
        (errors.CrsRequiredError, "CRS_REQUIRED", 422),
        (errors.ModelsNotLoadedError, "MODELS_NOT_LOADED", 503),
    ],
)
def test_error_codes_match_api_error_model(
    cls: type[errors.SonarSentinelError], code: str, status: int
) -> None:
    err = cls("message", key="value")
    assert isinstance(err, errors.SonarSentinelError)
    assert err.code == code
    assert err.http_status == status
    assert err.to_dict() == {
        "error": {"code": code, "message": "message", "details": {"key": "value"}}
    }
