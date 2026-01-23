from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3

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

crochet_db: List[CrochetItem] = []


@app.get("/crochet", response_model=List[CrochetItem])
def list_crochet():
    return crochet_db


@app.post("/crochet", response_model=CrochetItem)
def add_crochet(payload: CrochetCreate):
    item = CrochetItem(id=str(uuid4()), **payload.model_dump())
    crochet_db.insert(0, item)  # nuevo arriba
    return item


@app.patch("/crochet/{item_id}/toggle", response_model=CrochetItem)
def toggle_crochet(item_id: str):
    for i, item in enumerate(crochet_db):
        if item.id == item_id:
            new_status = "done" if item.status != "done" else "wip"
            updated = item.model_copy(update={"status": new_status})
            crochet_db[i] = updated
            return updated
    raise HTTPException(status_code=404, detail="Crochet item not found")


@app.delete("/crochet/{item_id}")
def delete_crochet(item_id: str):
    for i, item in enumerate(crochet_db):
        if item.id == item_id:
            crochet_db.pop(i)
            return {"ok": True}
    raise HTTPException(status_code=404, detail="Crochet item not found")


