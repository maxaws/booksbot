import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import models
from database import engine
from routers import apporteurs, commissions, dashboard, opportunites

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="One System CRM", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(apporteurs.router, prefix="/api/apporteurs", tags=["apporteurs"])
app.include_router(opportunites.router, prefix="/api/opportunites", tags=["opportunites"])
app.include_router(commissions.router, prefix="/api/commissions", tags=["commissions"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])

# Serve built React frontend in production
_frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def serve_spa(full_path: str):
        index = os.path.join(_frontend_dist, "index.html")
        return FileResponse(index)
