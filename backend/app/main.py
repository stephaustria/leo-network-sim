from fastapi import FastAPI

app = FastAPI(title="LEO Network Simulator")


@app.get("/health")
def health():
    return {"status": "ok"}