from fastapi import FastAPI

from app.api.constellation import router as constellation_router

app = FastAPI(title="LEO Network Simulator")
app.include_router(constellation_router)


@app.get("/health")
def health():
    return {"status": "ok"}