"""ORM tables of the prototype SQLite database (``docs/architecture/06-data-models.md`` §6).

Timestamps are ISO 8601 UTC strings. Additions to the ER model, needed by the API:
``job.created_utc``, ``job.pings_done``, ``job.pings_total`` and ``job.warnings_json``
(``GET /jobs/{job_id}``), and ``detection.detection_json``, the full report detection, so API
responses and exports never depend on the column subset.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Project(Base):
    __tablename__ = "project"

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    created_utc: Mapped[str] = mapped_column(String)


class Survey(Base):
    __tablename__ = "survey"

    survey_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(ForeignKey("project.project_id"))
    name: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    start_utc: Mapped[str | None] = mapped_column(String)
    end_utc: Mapped[str | None] = mapped_column(String)
    track_length_km: Mapped[float | None] = mapped_column(Float)
    bbox_wkt: Mapped[str | None] = mapped_column(Text)
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    config_hash: Mapped[str | None] = mapped_column(String)
    created_utc: Mapped[str] = mapped_column(String)


class SourceFile(Base):
    __tablename__ = "source_file"

    file_id: Mapped[str] = mapped_column(String, primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey.survey_id"), index=True)
    filename: Mapped[str] = mapped_column(String)
    format: Mapped[str] = mapped_column(String)
    size_bytes: Mapped[int] = mapped_column(Integer)
    pings: Mapped[int | None] = mapped_column(Integer)
    sonar_json: Mapped[str | None] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String)


class Job(Base):
    __tablename__ = "job"

    job_id: Mapped[str] = mapped_column(String, primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey.survey_id"), unique=True)
    status: Mapped[str] = mapped_column(String)
    stage: Mapped[str | None] = mapped_column(String)
    percent: Mapped[float] = mapped_column(Float, default=0.0)
    pings_done: Mapped[int | None] = mapped_column(Integer)
    pings_total: Mapped[int | None] = mapped_column(Integer)
    stage_timings_json: Mapped[str] = mapped_column(Text, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, default="[]")
    error_json: Mapped[str | None] = mapped_column(Text)
    created_utc: Mapped[str] = mapped_column(String)
    started_utc: Mapped[str | None] = mapped_column(String)
    finished_utc: Mapped[str | None] = mapped_column(String)


class ModelVersion(Base):
    __tablename__ = "model_version"

    model_version_id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String)
    metrics_json: Mapped[str | None] = mapped_column(Text)


class Detection(Base):
    __tablename__ = "detection"
    __table_args__ = (
        Index("ix_detection_survey_tier_confidence", "survey_id", "alert_tier", "confidence"),
        Index("ix_detection_cls", "cls"),
        Index("ix_detection_review_status", "review_status"),
    )

    detection_id: Mapped[str] = mapped_column(String, primary_key=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey.survey_id"))
    model_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("model_version.model_version_id")
    )
    cls: Mapped[str] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float)
    alert_tier: Mapped[str] = mapped_column(String)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    footprint_wkt: Mapped[str | None] = mapped_column(Text)
    depth_m: Mapped[float | None] = mapped_column(Float)
    uncertainty_m: Mapped[float | None] = mapped_column(Float)
    length_m: Mapped[float | None] = mapped_column(Float)
    width_m: Mapped[float | None] = mapped_column(Float)
    area_m2: Mapped[float | None] = mapped_column(Float)
    height_m: Mapped[float | None] = mapped_column(Float)
    orientation_deg: Mapped[float | None] = mapped_column(Float)
    side: Mapped[str | None] = mapped_column(String)
    ping_start: Mapped[int | None] = mapped_column(Integer)
    ping_end: Mapped[int | None] = mapped_column(Integer)
    ground_range_m: Mapped[float | None] = mapped_column(Float)
    scores_json: Mapped[str] = mapped_column(Text)
    quality_flags: Mapped[str] = mapped_column(Text, default="")
    n_views: Mapped[int] = mapped_column(Integer, default=1)
    review_status: Mapped[str] = mapped_column(String, default="pending")
    chip_path: Mapped[str | None] = mapped_column(String)
    mask_rle: Mapped[str | None] = mapped_column(Text)
    detection_json: Mapped[str] = mapped_column(Text)


class Review(Base):
    __tablename__ = "review"

    review_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    detection_id: Mapped[str] = mapped_column(ForeignKey("detection.detection_id"), index=True)
    reviewer: Mapped[str | None] = mapped_column(String)
    action: Mapped[str] = mapped_column(String)
    old_cls: Mapped[str | None] = mapped_column(String)
    new_cls: Mapped[str | None] = mapped_column(String)
    reject_reason: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text)
    created_utc: Mapped[str] = mapped_column(String)


class TrackSegment(Base):
    __tablename__ = "track_segment"

    segment_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey.survey_id"), index=True)
    ping_start: Mapped[int | None] = mapped_column(Integer)
    ping_end: Mapped[int | None] = mapped_column(Integer)
    line_wkt: Mapped[str] = mapped_column(Text)


class QualityEvent(Base):
    __tablename__ = "quality_event"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey.survey_id"), index=True)
    code: Mapped[str] = mapped_column(String)
    ping_start: Mapped[int | None] = mapped_column(Integer)
    ping_end: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)


class Report(Base):
    __tablename__ = "report"

    report_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    survey_id: Mapped[str] = mapped_column(ForeignKey("survey.survey_id"), index=True)
    format: Mapped[str] = mapped_column(String)
    path: Mapped[str] = mapped_column(Text)
    created_utc: Mapped[str] = mapped_column(String)
