from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from yawc_routes import router

app = FastAPI(title="YAWC API", version="5.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=False)
