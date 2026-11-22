from fastapi import FastAPI

from app.routers import auth, campaigns, drafts, leads, sending, stats, suppressions, unsubscribe, workspace

# The database schema is managed by Alembic, not created here. Run `alembic upgrade head`
# before starting the app (the Dockerfile does this for you).

app = FastAPI(title="LeadFlow API", version="0.1.0")
app.include_router(auth.router)
app.include_router(campaigns.router)
app.include_router(leads.router)
app.include_router(suppressions.router)
app.include_router(workspace.router)
app.include_router(drafts.router)
app.include_router(sending.router)
app.include_router(stats.router)
app.include_router(unsubscribe.router)


@app.get("/health")
def health():
    return {"status": "ok"}
