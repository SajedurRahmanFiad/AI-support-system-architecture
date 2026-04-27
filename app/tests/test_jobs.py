from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from app.services import jobs


class _DeadThread:
    def is_alive(self) -> bool:
        return False


class _StartedThread:
    def __init__(self, *args, **kwargs) -> None:
        self.started = False

    def start(self) -> None:
        self.started = True

    def is_alive(self) -> bool:
        return self.started


class _RunnerSentinel:
    def __init__(self) -> None:
        self.stop_called = False

    def stop(self) -> None:
        self.stop_called = True


def test_background_job_runner_restarts_when_thread_is_dead(monkeypatch):
    created_threads: list[_StartedThread] = []

    def fake_thread(*args, **kwargs):
        thread = _StartedThread(*args, **kwargs)
        created_threads.append(thread)
        return thread

    monkeypatch.setattr(jobs, "_log_job_runner", lambda message: None)
    monkeypatch.setattr(jobs.threading, "Thread", fake_thread)

    runner = jobs.BackgroundJobRunner()
    runner.settings.job_runner_enabled = True
    runner._thread = _DeadThread()

    runner.start()

    assert len(created_threads) == 1
    assert runner._thread is created_threads[0]
    assert created_threads[0].started is True


def test_stop_background_job_runner_respects_persistent_env(monkeypatch):
    sentinel = _RunnerSentinel()

    monkeypatch.setenv("PERSIST_BACKGROUND_JOB_RUNNER", "1")
    monkeypatch.setattr(jobs, "_shared_runner", sentinel)

    jobs.stop_background_job_runner()

    assert sentinel.stop_called is False
    assert jobs._shared_runner is sentinel


def test_schedule_background_job_processing_spawns_detached_worker(monkeypatch):
    captured: dict[str, object] = {}

    def fake_popen(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setenv("PERSIST_BACKGROUND_JOB_RUNNER", "1")
    monkeypatch.setattr(jobs, "get_settings", lambda: SimpleNamespace(job_runner_batch_size=24))
    monkeypatch.setattr(jobs.subprocess, "Popen", fake_popen)

    jobs.schedule_background_job_processing(datetime.now(timezone.utc))

    assert captured["args"][0][0] == jobs.sys.executable
    assert captured["args"][0][1] == "-c"
    assert captured["kwargs"]["start_new_session"] is True
