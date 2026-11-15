# PDF ↔ DOCX konverter

Ez a projekt PDF- és DOCX-dokumentumok átalakítására szolgáló webalkalmazás. A backend Python és FastAPI, a frontend React és TypeScript, az adattárolás PostgreSQL-alapú.

A jelenlegi verzióban regisztráció, bejelentkezés, profiladatok megtekintése, kijelentkezés, fióktörlés és PDF ↔ DOCX konverzió érhető el. A konvertálás bejelentkezés nélkül is használható. A bejelentkezett felhasználók konverziói megjelennek a profiloldal előzményeiben, és az eredményfájlok onnan újra letölthetők. A vendégként végzett konverziók nem kerülnek mentésre. Egy fájl legfeljebb 25 MB lehet. A bejelentkezett felhasználók eredményei a `STORAGE_PATH` könyvtárba kerülnek; Docker Compose esetén a `converter-data` volume őrzi meg őket. A fiók törlése a mentett eredményeket is eltávolítja.

## Helyi környezet reprodukálása

Szükséges: Docker és Docker Compose.

```sh
cp .env.example .env
docker compose up --build
```

Az API indulásakor az adatbázis-migrációk automatikusan lefutnak. A PostgreSQL-adatok a `postgres-data` nevű Docker volume-ban maradnak meg. A migrációs fájlok készítésének és futtatásának leírása: [MIGRACIOK.md](MIGRACIOK.md).

## Elérési pontok

- Kezdőlap és munkafelület: <http://localhost:5173/>
- Bejelentkezés és regisztráció: <http://localhost:5173/auth>
- Munkafelület belépési útvonala: <http://localhost:5173/auth/workspace>
- Profil: <http://localhost:5173/profile>
- API dokumentáció: <http://localhost:8000/docs>
- API állapot: <http://localhost:8000/api/health>
- API és adatbázis állapota: <http://localhost:8000/api/health/ready>

A szolgáltatások leállítása: `docker compose down`.

## Automatizált ellenőrzések

Az API-tesztek külön, memóriabeli SQLite-adatbázist használnak.

GitHub Actions minden pushnál és pull requestnél lefuttatja a backendteszteket, valamint elkészíti a frontend buildet.

**Virtuális környezet létrehozása:** `python3 -m venv .venv`.

**Tesztfüggőségek telepítése:** `.venv/bin/python -m pip install -r backend/requirements.txt -r backend/requirements-dev.txt`.

**Backend tesztek futtatása:** `.venv/bin/python -m pytest backend/tests`.

Debian/Ubuntu rendszeren, ha a virtuális környezet létrehozása nem sikerül: `sudo apt install python3-venv`.

**Frontend build ellenőrzése Dockerrel:**

```sh
docker run --rm \
  -v "$PWD/frontend:/app" \
  -v /app/node_modules \
  -w /app \
  node:22-bookworm-slim \
  sh -c 'npm ci && npm run build'
```

## API-funkciók

- `POST /api/auth/register` — regisztráció e-mail-címmel és jelszóval.
- `POST /api/auth/login` — bejelentkezés.
- `POST /api/auth/refresh` — refresh cookie cseréje és új access token kiadása.
- `POST /api/auth/logout` — refresh session visszavonása és cookie törlése.
- `GET /api/auth/me` — bejelentkezett felhasználó adatainak lekérése.
- `DELETE /api/auth/me` — saját fiók törlése jelszóval megerősítve.
- `POST /api/conversions/pdf-to-docx` — PDF fájl átalakítása DOCX dokumentummá; a `file` mező multipart fájlfeltöltést vár.
- `POST /api/conversions/docx-to-pdf` — DOCX dokumentum átalakítása PDF-fé; a `file` mező multipart fájlfeltöltést vár.
- `GET /api/conversions/history` — a bejelentkezett felhasználó saját konverziós előzményei.
- `GET /api/conversions/history/{conversion_id}/download` — saját konverzió eredményfájljának letöltése.

A PDF → DOCX átalakítást a `pdf2docx`, a DOCX → PDF átalakítást a Docker-képbe telepített LibreOffice végzi. A LibreOffice helyi futtatásához külön telepítése szükséges.

A jelszavak Argon2 hashként, a refresh tokenek SHA-256 hashként kerülnek az adatbázisba. A refresh token HttpOnly, SameSite=Lax cookie-ban van, és minden frissítéskor új tokenre cserélődik. Az access token alapértelmezett élettartama 15 perc, a refresh tokené legfeljebb 30 nap. Éles HTTPS-környezetben a `REFRESH_COOKIE_SECURE=true` beállítás szükséges.

## Projektfájlok

- `backend/` — FastAPI API, adatmodellek és Alembic-migrációk.
- `frontend/` — React + TypeScript + Vite felület.
- `compose.yaml` — helyi fejlesztői környezet.
- `.env.example` — helyi konfiguráció mintája.

Valódi hozzáférési titok nem kerülhet a Gitbe.
