from kurgu_api.worker import WorkerSettings, ping


async def test_ping_job() -> None:
    assert await ping({}) == "pong"
    assert "ping" in {
        getattr(f, "__name__", getattr(f, "name", None)) for f in WorkerSettings.functions
    }
