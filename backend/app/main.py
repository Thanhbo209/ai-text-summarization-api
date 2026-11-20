from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()


@app.get("/")
def home():
    return {"message": "Hello World"}


@app.get("/health")
def health():
    return {"status": "ok"}


client = TestClient(app)
