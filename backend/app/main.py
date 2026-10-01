from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.constellation import router as constellation_router
from app.api.links import router as links_router
from app.api.runs import router as runs_router
from app.api.simulation import router as simulation_router
from app.api.topology import router as topology_router
from app.api.ws import router as ws_router
from app.db.models import Base
from app.db.session import engine



@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)   # creates tables if missing
    yield


app = FastAPI(title="LEO Network Simulator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(constellation_router)
app.include_router(links_router)
app.include_router(topology_router)
app.include_router(simulation_router)
app.include_router(runs_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    return {"status": "ok"}