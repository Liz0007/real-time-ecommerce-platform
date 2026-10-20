"""Tests for app.supervision.watch. Run with: python -m pytest tests/test_supervision.py"""

import asyncio

from app.supervision import watch


class ExitCalled(Exception):
    pass


def _run(worker, stop_before_finish: bool):
    exits = []

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(worker(stop))
        watch(task, stop, "test worker", _exit=exits.append)
        if stop_before_finish:
            stop.set()
        try:
            await task
        except Exception:
            pass
        await asyncio.sleep(0)  # let the done-callback run

    asyncio.run(scenario())
    return exits


async def crashing_worker(stop):
    await asyncio.sleep(0)
    raise ConnectionError("database went away")


async def well_behaved_worker(stop):
    while not stop.is_set():
        await asyncio.sleep(0)


async def worker_that_returns_early(stop):
    return None


def test_a_crashing_worker_exits_the_process_with_status_1():
    assert _run(crashing_worker, stop_before_finish=False) == [1]


def test_a_worker_that_returns_while_running_also_exits():
    assert _run(worker_that_returns_early, stop_before_finish=False) == [1]


def test_normal_shutdown_does_not_exit():
    assert _run(well_behaved_worker, stop_before_finish=True) == []


def test_cancelled_worker_does_not_exit():
    exits = []

    async def scenario():
        stop = asyncio.Event()
        task = asyncio.create_task(well_behaved_worker(stop))
        watch(task, stop, "test worker", _exit=exits.append)
        await asyncio.sleep(0)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await asyncio.sleep(0)

    asyncio.run(scenario())
    assert exits == []
