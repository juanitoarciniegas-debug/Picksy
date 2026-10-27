from fastapi import FastAPI
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware

from auth import router as auth_router
from busqueda import router as busqueda_router
from historial import router as historial_router

app = FastAPI(title="Picksy API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ],
    allow_methods=["GET", "POST", "DELETE"],  # DELETE: borrar historial
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(busqueda_router)
app.include_router(historial_router)


@app.get("/")
def inicio():
    return {"mensaje": "Picksy funcionando"}

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)