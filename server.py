import os
import json
from typing import Any, Optional

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uuid import uuid4

# ========= DB =========
DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(DATABASE_URL)

def init_tables():
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Estado (guardamos JSON para current_book y finished_books)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL
                )
            """)
            # Crochet
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crochet (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    notes TEXT,
                    status TEXT NOT NULL
                )
            """)
        conn.commit()

def get_state(key: str, default: Any):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value::text FROM state WHERE key = %s", (key,))
            row = cur.fetchone()
    if not row:
        return default
    return json.loads(row[0])

def set_state(key: str, value: Any):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO state (key, value)
                VALUES (%s, %s::jsonb)
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
                """,
                (key, json.dumps(value)),
            )
        conn.commit()

# ========= APP =========
app = FastAPI()

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://magnificent-panda-edbec6.netlify.app",
    "https://luxury-begonia-2136b4.netlify.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup():
    # Importante: inicializamos tablas al arrancar
    init_tables()

@app.get("/ping")
def ping():
    return {"ok": True, "msg": "pong 💜"}

@app.get("/marker")
def marker():
    return {"marker": "SERVER_PY_NEW_123"}

@app.get("/")
def root():
    return {"ok": True, "msg": "Lilazul API online 💜"}

# ========= CURRENT BOOK =========
class CurrentBook(BaseModel):
    title: str

@app.get("/current-book")
def get_current_book():
    return get_state("current_book", {})

@app.post("/current-book")
def set_current_book(payload: CurrentBook):
    data = payload.model_dump()
    set_state("current_book", data)
    return data

# ========= FINISHED BOOKS =========
class FinishedBook(BaseModel):
    id: Optional[str] = None
    title: str
    date: str

@app.get("/finished-books")
def list_finished_books():
    return get_state("finished_books", [])

@app.post("/finished-books")
def add_finished_book(payload: FinishedBook):
    books = get_state("finished_books", [])
    item = payload.model_dump()
    if not item.get("id"):
        item["id"] = str(uuid4())
    books.insert(0, item)
    set_state("finished_books", books)
    return books

@app.delete("/finished-books/{book_id}")
def delete_finished_book(book_id: str):
    books = get_state("finished_books", [])
    new_books = [b for b in books if str(b.get("id")) != str(book_id)]
    if len(new_books) == len(books):
        raise HTTPException(status_code=404, detail="Book not found")
    set_state("finished_books", new_books)
    return {"ok": True}

# ========= CROCHET =========
class CrochetCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    status: Optional[str] = "wip"  # wip/done

class CrochetItem(CrochetCreate):
    id: str

@app.get("/crochet", response_model=list[CrochetItem])
def list_crochet():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, notes, status FROM crochet ORDER BY id DESC")
            rows = cur.fetchall()
    return [CrochetItem(id=r[0], title=r[1], notes=r[2] or "", status=r[3]) for r in rows]

@app.post("/crochet", response_model=CrochetItem)
def add_crochet(payload: CrochetCreate):
    item_id = str(uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO crochet (id, title, notes, status) VALUES (%s, %s, %s, %s)",
                (item_id, payload.title, payload.notes or "", payload.status or "wip"),
            )
        conn.commit()
    return CrochetItem(id=item_id, title=payload.title, notes=payload.notes or "", status=payload.status or "wip")

@app.patch("/crochet/{item_id}/toggle", response_model=CrochetItem)
def toggle_crochet(item_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT title, notes, status FROM crochet WHERE id = %s", (item_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Crochet item not found")
            new_status = "done" if row[2] != "done" else "wip"
            cur.execute("UPDATE crochet SET status = %s WHERE id = %s", (new_status, item_id))
        conn.commit()
    return CrochetItem(id=item_id, title=row[0], notes=row[1] or "", status=new_status)

@app.delete("/crochet/{item_id}")
def delete_crochet(item_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM crochet WHERE id = %s", (item_id,))
            deleted = cur.rowcount
        conn.commit()
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Crochet item not found")
    return {"ok": True}



