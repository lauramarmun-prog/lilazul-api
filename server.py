from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

import os
import psycopg

import json
from typing import Any


from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import os
import psycopg

DATABASE_URL = os.getenv("DATABASE_URL")

def get_conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL no está configurada")
    return psycopg.connect(DATABASE_URL)
def init_crochet_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS crochet (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    notes TEXT,
                    status TEXT NOT NULL
                )
            """)
        conn.commit()app = FastAPI()
def init_state_table():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS state (
                    key TEXT PRIMARY KEY,
                    value JSONB NOT NULL
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

app = FastAPI()

init_crochet_table()
init_state_table()


DB = "lilazul.db"


def init_db():
    con = sqlite3.connect(DB)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS finished_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS crochet (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    con.commit()
    con.close()


def db():
    # check_same_thread False ayuda a evitar algunos líos con sqlite en servidores
    return sqlite3.connect(DB, check_same_thread=False)


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI()

ALLOWED_ORIGINS = [
    "http://127.0.0.1:5500",
    "http://localhost:5500",
    "https://magnificent-panda-edbec6.netlify.app",
    # opcional si tienes otro deploy viejo:
    "https://luxury-begonia-2136b4.netlify.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 👇 útil para probar CORS rápido
@app.get("/ping")
def ping():
    return {"ok": True, "msg": "pong 💜"}


@app.get("/")
def root():
    return {"ok": True, "msg": "Lilazul API online 💜"}

@app.get("/ping")
def ping():
    return {"ok": True, "cors": "enabled", "version": "2026-01-23"}

init_db()


class CurrentBook(BaseModel):
    title: str


class FinishedBook(BaseModel):
    title: str
    date: str


class CrochetItem(BaseModel):
    name: str
    status: str


# ========= CURRENT BOOK =========
@app.get("/current-book")
def get_current_book():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT value FROM state WHERE key='current_book'")
    row = cur.fetchone()
    con.close()
    return {"title": row[0] if row else ""}


@app.post("/current-book")
def set_current_book(payload: CurrentBook):
    con = db()
    cur = con.cursor()
    cur.execute(
        """
        INSERT INTO state(key,value)
        VALUES('current_book', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (payload.title,),
    )
    con.commit()
    con.close()
    return {"ok": True}


# ========= FINISHED BOOKS =========
@app.get("/finished-books")
def list_finished_books():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, title, date FROM finished_books ORDER BY id DESC")
    rows = cur.fetchall()
    con.close()
    return [{"id": r[0], "title": r[1], "date": r[2]} for r in rows]


@app.post("/finished-books")
def add_finished_book(payload: FinishedBook):
    con = db()
    cur = con.cursor()
    cur.execute(
        "INSERT INTO finished_books(title, date) VALUES(?, ?)",
        (payload.title, payload.date),
    )
    con.commit()
    con.close()
    return {"ok": True}


@app.delete("/finished-books/{book_id}")
def delete_finished_book(book_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM finished_books WHERE id=?", (book_id,))
    con.commit()
    con.close()
    return {"ok": True}


# ========= CROCHET (SERVER) =========
from pydantic import BaseModel
from typing import Optional, List
from uuid import uuid4

class CrochetCreate(BaseModel):
    title: str
    notes: Optional[str] = ""
    status: Optional[str] = "wip"  # "wip" o "done"

class CrochetItem(CrochetCreate):
    id: str

# crochet_db: List[CrochetItem] = []



@app.get("/crochet", response_model=list[CrochetItem])
def list_crochet():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, title, notes, status FROM crochet ORDER BY rowid DESC")
            rows = cur.fetchall()

    return [
        CrochetItem(id=r[0], title=r[1], notes=r[2] or "", status=r[3])
        for r in rows
    ]



@app.post("/crochet", response_model=CrochetItem)
def add_crochet(payload: CrochetCreate):
    item_id = str(uuid4())
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO crochet (id, title, notes, status) VALUES (%s, %s, %s, %s)",
                (item_id, payload.title, payload.notes or "", payload.status),
            )
        conn.commit()

    return CrochetItem(
        id=item_id,
        title=payload.title,
        notes=payload.notes or "",
        status=payload.status,
    )


@app.patch("/crochet/{item_id}/toggle", response_model=CrochetItem)
def toggle_crochet(item_id: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT title, notes, status FROM crochet WHERE id = %s",
                (item_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Crochet item not found")

            new_status = "done" if row[2] != "done" else "wip"
            cur.execute(
                "UPDATE crochet SET status = %s WHERE id = %s",
                (new_status, item_id),
            )
        conn.commit()

    return CrochetItem(
        id=item_id,
        title=row[0],
        notes=row[1] or "",
        status=new_status,
    )



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



