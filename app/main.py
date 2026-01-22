from fastapi import FastAPI, Depends
from contextlib import asynccontextmanager
from strawberry.fastapi import GraphQLRouter
from app.core.database import engine, Base, get_db
from app.api.v1.endpoints import router as api_router
from app.graphql.schema import schema

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

app = FastAPI(title="Invoice Reconciliation API", lifespan=lifespan)

app.include_router(api_router, prefix="/api/v1")

async def get_context(db=Depends(get_db)):
    return {"db": db}

graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")

@app.get("/")
async def root():
    return {"message": "Invoice Reconciliation API is running"}
