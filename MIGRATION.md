# Adatbázis-migrációk

A projekt SQLAlchemy modelleket és Alembicet használ az adatbázis szerkezetének kezelésére.

**Modell:** `backend/app/models.py`.

**Adatbázis és API indítása:**

```sh
docker compose up -d db api
```

**Migrációs fájl készítése:**

```sh
docker compose exec api alembic revision --autogenerate -m "uj tabla"
```

**Migrációs fájl helye:** `backend/alembic/versions/`.

**Generált módosítások ellenőrzése:** a migrációs fájl átnézése futtatás előtt.

**Migráció futtatása:**

```sh
docker compose exec api alembic upgrade head
```

Az API indulásakor az `alembic upgrade head` parancs automatikusan lefut.

**Aktuális adatbázis-verzió ellenőrzése:**

```sh
docker compose exec api alembic current
```
