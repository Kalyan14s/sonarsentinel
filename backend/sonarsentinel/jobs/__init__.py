"""Processing jobs (ST-082): queue, worker thread, cancellation and result persistence."""

from sonarsentinel.jobs.manager import JobManager, JobRequest

__all__ = ["JobManager", "JobRequest"]
