from __future__ import annotations

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
