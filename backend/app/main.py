from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.deps import get_moon_director, get_rule_engine, get_world_state_manager
from app.api.http_routes import router as http_router
from app.api.websocket_routes import manager, router as websocket_router
from app.core.constants import PROJECT_NAME
from app.db.sqlite import init_db
from app.runtime.game_loop import GameLoop


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    game_loop = GameLoop(
        state_manager=get_world_state_manager(),
        rule_engine=get_rule_engine(),
        director=get_moon_director(),
        broadcast=manager.broadcast,
    )
    await game_loop.start()
    app.state.game_loop = game_loop
    yield
    await game_loop.stop()


app = FastAPI(title="Moonfall Runtime", version="0.1.0", lifespan=lifespan)
app.include_router(http_router)
app.include_router(websocket_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {"service": PROJECT_NAME, "docs": "/docs", "health": "/api/health"}
