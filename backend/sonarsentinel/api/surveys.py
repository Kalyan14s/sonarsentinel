"""Survey upload and job endpoints (ST-081, ST-082; API spec §2.1, §2.2, §2.7).

Uploads are streamed part by part to disk, never buffered whole in memory, and a file is rejected
with ``FILE_TOO_LARGE`` as soon as it passes ``ingest.max_upload_gb``. File names are reduced to a
safe basename, and formats are checked by extension and magic bytes (stage S0) before a job is
queued. ``POST /surveys/validate`` reads the same form into a temporary folder that is removed
afterwards, so nothing is processed or kept.
"""

from __future__ import annotations

import gc
import hashlib
import json
import re
import secrets
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal, cast

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticValidationError
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import MultipartParser, parse_options_header

from sonarsentinel.api.context import ApiContext, get_context
from sonarsentinel.errors import (
    FileTooLargeError,
    NavCsvInvalidError,
    NotFoundError,
    SonarSentinelError,
    UnsupportedFormatError,
    ValidationError,
)
from sonarsentinel.ingest.models import NOT_GEOTAGGED
from sonarsentinel.ingest.reader import read_source, summarize
from sonarsentinel.ingest.validators import check_file
from sonarsentinel.jobs.manager import JobRequest
from sonarsentinel.storage import repository as repo
from sonarsentinel.storage.models import Job

router = APIRouter()

DETECTOR_MODELS = ("auto", "classical", "yolo")
IMAGE_FORMATS = ("png", "jpeg")
SURVEY_FORMATS = ("xtf", "geotiff", "png", "jpeg")
MAX_FIELD_BYTES = 64 * 1024
NO_NAVIGATION = "NO_NAVIGATION: attach a navigation CSV or continue without GPS"
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


class SurveyOptions(BaseModel):
    """The ``options`` JSON of ``POST /surveys`` (API spec §2.1).

    ``min_conf`` is an addition for the upload screen's "Min. shown" setting.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    name: str | None = None
    project: str | None = None
    utm_epsg: int | Literal["auto"] = "auto"
    ground_resolution_m: float = Field(default=0.10, gt=0, le=10)
    apply_layback: Literal["auto"] | bool = "auto"
    manual_layback_m: float | None = Field(default=None, ge=0)
    anomaly_scan: bool = True
    image_layout: Literal["port_stbd", "port_only", "stbd_only"] = "port_stbd"
    allow_no_gps: bool = False
    detector_model: str = "auto"
    min_conf: float | None = Field(default=None, ge=0, le=100)

    @field_validator("utm_epsg", mode="before")
    @classmethod
    def _epsg_digits(cls, value: Any) -> Any:
        return int(value) if isinstance(value, str) and value.isdigit() else value

    @field_validator("apply_layback", mode="before")
    @classmethod
    def _layback_words(cls, value: Any) -> Any:
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        return value


def parse_options(raw: str | None) -> SurveyOptions:
    """Validate the ``options`` form field; unknown keys and wrong types are 400 errors."""
    if raw is None or not raw.strip():
        return SurveyOptions()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError(
            "options must be a JSON object", field="options", reason=str(exc)
        ) from exc
    if not isinstance(data, dict):
        raise ValidationError("options must be a JSON object", field="options")
    try:
        options = SurveyOptions.model_validate(data)
    except PydanticValidationError as exc:
        errors = [
            {"field": ".".join(str(p) for p in err["loc"]) or "options", "message": err["msg"]}
            for err in exc.errors()
        ]
        raise ValidationError("Invalid options", field="options", errors=errors) from exc
    if options.detector_model not in DETECTOR_MODELS:
        raise ValidationError(
            f"Unknown detector_model: {options.detector_model}",
            field="detector_model",
            supported=list(DETECTOR_MODELS),
        )
    return options


def safe_filename(name: str) -> str:
    """Basename with only letters, digits, ``.``, ``_`` and ``-`` (no paths, no hidden files)."""
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _UNSAFE.sub("_", base).lstrip("._")
    if not cleaned:
        return "upload"
    path = Path(cleaned)
    return path.stem[:100] + path.suffix[:20] if len(cleaned) > 120 else cleaned


def _unique(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        n += 1
        candidate = path.with_name(f"{path.stem}-{n}{path.suffix}")
    return candidate


@dataclass
class UploadedPart:
    """One uploaded file: client name, where it was stored, size and checksum."""

    field: str
    filename: str
    path: Path
    size_bytes: int = 0
    sha256: str = ""
    too_large: bool = False


@dataclass
class UploadForm:
    files: list[UploadedPart] = field(default_factory=list)
    nav_csv: UploadedPart | None = None
    fields: dict[str, str] = field(default_factory=dict)


class _FormReader:
    """Streaming multipart callbacks: files go to ``target``, text fields stay in memory."""

    def __init__(self, target: Path, max_bytes: int) -> None:
        self.target = target
        self.max_bytes = max_bytes
        self.form = UploadForm()
        self.error: SonarSentinelError | None = None
        self.oversized: UploadedPart | None = None
        self._header_name = bytearray()
        self._header_value = bytearray()
        self._headers: dict[bytes, bytes] = {}
        self._part: UploadedPart | None = None
        self._field: str | None = None
        self._value = bytearray()
        self._handle: IO[bytes] | None = None
        self._digest: Any = None

    def callbacks(self) -> dict[str, Any]:
        return {
            "on_part_begin": self._part_begin,
            "on_header_field": self._header_field,
            "on_header_value": self._header_value_data,
            "on_header_end": self._header_end,
            "on_headers_finished": self._headers_finished,
            "on_part_data": self._part_data,
            "on_part_end": self._part_end,
        }

    def _part_begin(self) -> None:
        self._headers = {}
        self._part = None
        self._field = None
        self._value = bytearray()

    def _header_field(self, data: bytes, start: int, end: int) -> None:
        self._header_name += data[start:end]

    def _header_value_data(self, data: bytes, start: int, end: int) -> None:
        self._header_value += data[start:end]

    def _header_end(self) -> None:
        self._headers[bytes(self._header_name).lower()] = bytes(self._header_value)
        self._header_name = bytearray()
        self._header_value = bytearray()

    def _headers_finished(self) -> None:
        _, params = parse_options_header(self._headers.get(b"content-disposition", b""))
        name = params.get(b"name", b"").decode("utf-8", "replace")
        filename = params.get(b"filename")
        if filename is None:
            self._field = name
            return
        client_name = filename.decode("utf-8", "replace")
        path = _unique(self.target / safe_filename(client_name))
        self._part = UploadedPart(field=name, filename=client_name, path=path)
        self._handle = path.open("wb")
        self._digest = hashlib.sha256()

    def _part_data(self, data: bytes, start: int, end: int) -> None:
        chunk = data[start:end]
        part = self._part
        if part is None:
            if self._field is None:
                return
            if len(self._value) + len(chunk) > MAX_FIELD_BYTES:
                self.error = self.error or ValidationError(
                    f"Form field {self._field} is too long",
                    field=self._field,
                    max_bytes=MAX_FIELD_BYTES,
                )
            else:
                self._value += chunk
            return
        part.size_bytes += len(chunk)
        if part.too_large:
            return
        if part.size_bytes > self.max_bytes:
            part.too_large = True
            self._close_file(delete=True)
            self.oversized = self.oversized or part
            return
        if self._handle is not None:
            self._handle.write(chunk)
            self._digest.update(chunk)

    def _part_end(self) -> None:
        part = self._part
        if part is not None:
            if not part.too_large:
                self._close_file(delete=False)
                part.sha256 = self._digest.hexdigest()
            if part.field == "files":
                self.form.files.append(part)
            elif part.field == "nav_csv":
                self.form.nav_csv = part
            else:
                part.path.unlink(missing_ok=True)  # unknown file fields are ignored
        elif self._field is not None:
            self.form.fields[self._field] = self._value.decode("utf-8", "replace")
        self._part = None
        self._field = None

    def _close_file(self, *, delete: bool) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None
        if delete and self._part is not None:
            self._part.path.unlink(missing_ok=True)

    def close(self) -> None:
        self._close_file(delete=False)


def _too_large(part: UploadedPart, max_bytes: int) -> FileTooLargeError:
    limit_gb = max_bytes / 1024**3
    return FileTooLargeError(
        f"{part.filename} exceeds the {limit_gb:g} GB upload limit",
        filename=part.filename,
        max_bytes=max_bytes,
    )


async def read_form(
    request: Request, target: Path, max_bytes: int, *, reject_oversized: bool
) -> UploadForm:
    """Stream a ``multipart/form-data`` body; files are written under ``target``."""
    content_type, params = parse_options_header(request.headers.get("content-type", ""))
    boundary = params.get(b"boundary")
    if content_type != b"multipart/form-data" or not boundary:
        raise ValidationError("Send the files as multipart/form-data", field="files")
    reader = _FormReader(target, max_bytes)
    parser = MultipartParser(boundary, cast(Any, reader.callbacks()))
    try:
        async for chunk in request.stream():
            if chunk:
                await run_in_threadpool(parser.write, chunk)
            if reader.error is not None:
                raise reader.error
            if reject_oversized and reader.oversized is not None:
                raise _too_large(reader.oversized, max_bytes)
        parser.finalize()
    except MultipartParseError as exc:
        raise ValidationError("Malformed multipart body", field="files", reason=str(exc)) from exc
    finally:
        reader.close()
    return reader.form


def _check_survey_file(part: UploadedPart, max_bytes: int) -> str:
    if part.too_large:
        raise _too_large(part, max_bytes)
    fmt = check_file(part.path, max_bytes).source_format
    if fmt not in SURVEY_FORMATS:
        raise UnsupportedFormatError(
            f"{part.filename}: send a navigation CSV as nav_csv, not in files",
            filename=part.filename,
        )
    return fmt


def _check_nav(part: UploadedPart, max_bytes: int) -> None:
    if part.too_large:
        raise _too_large(part, max_bytes)
    if check_file(part.path, max_bytes).source_format != "csv":
        raise NavCsvInvalidError(f"{part.filename} is not a CSV file", filename=part.filename)


def _describe_file(
    part: UploadedPart,
    nav: UploadedPart | None,
    nav_error: SonarSentinelError | None,
    options: SurveyOptions,
    max_bytes: int,
    work_dir: Path,
) -> dict[str, Any]:
    """One entry of the validate response; errors become ``valid: false`` with the error body."""
    entry: dict[str, Any] = {
        "filename": part.filename,
        "valid": False,
        "format": Path(part.filename).suffix.lower().lstrip(".") or None,
        "size_bytes": part.size_bytes,
        "warnings": [],
    }
    try:
        fmt = _check_survey_file(part, max_bytes)
        is_image = fmt in IMAGE_FORMATS
        if is_image and nav_error is not None:
            raise nav_error
        log = read_source(
            part.path,
            nav_csv=nav.path if is_image and nav is not None else None,
            epsg=options.utm_epsg,
            layout=options.image_layout,
            allow_no_gps=True,
            work_dir=work_dir,
            max_bytes=max_bytes,
        )
    except SonarSentinelError as exc:
        return entry | {"warnings": [f"{exc.code}: {exc.message}"], "error": exc.to_dict()["error"]}

    info = summarize(log, part.size_bytes)
    warnings = [w for w in info["warnings"] if w != NOT_GEOTAGGED]
    if not log.has_navigation:
        warnings.insert(0, NO_NAVIGATION)
    info.update(filename=part.filename, warnings=warnings)
    if is_image:
        info["format"] = "image_nav" if log.has_navigation else "image_only"
        if log.image is not None:
            info["height"], info["width"] = int(log.image.shape[0]), int(log.image.shape[1])
    return info


def _describe_files(
    form: UploadForm, options: SurveyOptions, max_bytes: int, work_dir: Path
) -> list[dict[str, Any]]:
    nav_error: SonarSentinelError | None = None
    if form.nav_csv is not None:
        try:
            _check_nav(form.nav_csv, max_bytes)
        except SonarSentinelError as exc:
            nav_error = exc
    files = [
        _describe_file(part, form.nav_csv, nav_error, options, max_bytes, work_dir / f"{i:03d}")
        for i, part in enumerate(form.files)
    ]
    gc.collect()  # release memory-mapped XTF samples before the temporary folder is removed
    return files


@router.post(
    "/surveys/validate",
    tags=["surveys"],
    summary="Check files before processing (nothing is stored)",
)
async def validate_survey(request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    with tempfile.TemporaryDirectory(
        prefix="sonarsentinel-validate-", ignore_cleanup_errors=True
    ) as tmp:
        root = Path(tmp)
        form = await read_form(request, root, context.max_upload_bytes, reject_oversized=False)
        options = parse_options(form.fields.get("options"))
        if not form.files:
            raise ValidationError("Attach at least one file in 'files'", field="files")
        files = await run_in_threadpool(
            _describe_files, form, options, context.max_upload_bytes, root / "work"
        )
    return {"files": files}


def _register(
    context: ApiContext,
    staging: Path,
    form: UploadForm,
    formats: list[str],
    options: SurveyOptions,
) -> tuple[str, str]:
    """Reserve the survey ID, move the upload folder into place and create the DB rows."""
    day = datetime.now(UTC).strftime("%Y%m%d")
    with context.id_lock, context.database.session() as session, session.begin():
        survey_id = repo.next_survey_id(session, day)
        job_id = repo.new_job_id()
        target = staging.parent / survey_id
        staging.rename(target)
        try:
            repo.create_survey(
                session,
                survey_id=survey_id,
                job_id=job_id,
                name=options.name or Path(form.files[0].filename).stem,
                project=options.project,
                options=options.model_dump(),
                files=[
                    {
                        "filename": part.path.name,
                        "format": fmt,
                        "size_bytes": part.size_bytes,
                        "sha256": part.sha256,
                    }
                    for part, fmt in zip(form.files, formats, strict=True)
                ],
            )
            session.flush()
        except BaseException:
            target.rename(staging)
            raise
    return survey_id, job_id


@router.post(
    "/surveys",
    status_code=202,
    tags=["surveys"],
    summary="Upload files and start a processing job",
)
async def create_survey(request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    max_bytes = context.max_upload_bytes
    staging = context.data_dir / "uploads" / f".staging-{secrets.token_hex(6)}"
    staging.mkdir(parents=True)
    try:
        form = await read_form(request, staging, max_bytes, reject_oversized=True)
        options = parse_options(form.fields.get("options"))
        if not form.files:
            raise ValidationError("Attach at least one file in 'files'", field="files")
        formats = [_check_survey_file(part, max_bytes) for part in form.files]
        if form.nav_csv is not None:
            _check_nav(form.nav_csv, max_bytes)
        elif not options.allow_no_gps:
            images = [
                p.filename for p, f in zip(form.files, formats, strict=True) if f in IMAGE_FORMATS
            ]
            if images:
                raise ValidationError(
                    f"{images[0]} has no navigation: attach nav_csv or set allow_no_gps",
                    field="nav_csv",
                    files=images,
                    hint="allow_no_gps",
                )
        survey_id, job_id = await run_in_threadpool(
            _register, context, staging, form, formats, options
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    folder = context.data_dir / "uploads" / survey_id
    context.jobs.submit(
        JobRequest(
            job_id=job_id,
            survey_id=survey_id,
            sources=[folder / part.path.name for part in form.files],
            options=options.model_dump(),
            nav_csv=folder / form.nav_csv.path.name if form.nav_csv is not None else None,
        )
    )
    return {
        "survey_id": survey_id,
        "job_id": job_id,
        "status": "queued",
        "ws_url": f"/ws/jobs/{job_id}",
    }


@router.get("/jobs/{job_id}", tags=["jobs"], summary="Job status and stage timings")
def get_job(job_id: str, request: Request) -> dict[str, Any]:
    context = get_context(request.app)
    with context.database.session() as session:
        job = session.get(Job, job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found", job_id=job_id)
        return repo.job_payload(job)


@router.post(
    "/jobs/{job_id}/cancel",
    tags=["jobs"],
    summary="Cancel a queued (200) or running (202, stops within one chunk) job",
)
def cancel_job(job_id: str, request: Request) -> JSONResponse:
    status = get_context(request.app).jobs.cancel(job_id)
    return JSONResponse(
        status_code=200 if status == "cancelled" else 202,
        content={"job_id": job_id, "status": status},
    )
