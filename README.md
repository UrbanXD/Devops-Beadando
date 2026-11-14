# PDF ↔ DOCX konverter

Egy helyben futtatható webalkalmazás alapja PDF és DOCX dokumentumok átalakításához. A projekt Python API-t és React felületet használ. A konverziós motor, a tartós feladatkezelés és a helyreállítási folyamat a következő fejlesztési lépésben készül el.

## Indítás

Szükséges: Docker és Docker Compose.

```sh
cp .env.example .env
docker compose up --build
```

- React felület: <http://localhost:5173>
- API dokumentáció: <http://localhost:8000/docs>
- API állapot: <http://localhost:8000/api/health>

Leállítás: `docker compose down`. A konverziós fájlok később a `converter-data` nevű Docker volume-ba kerülnek, hogy a konténerek újraindítása ne törölje őket.

## Szerkezet

- `backend/` — FastAPI API
- `frontend/` — React + TypeScript + Vite
- `compose.yaml` — helyi fejlesztői környezet

## Következő fejlesztési lépések

1. Fájlfeltöltés, méret- és formátumellenőrzés.
2. Konverziós feladatok és állapotuk tartós tárolása.
3. PDF → DOCX és DOCX → PDF feldolgozás.
4. Eredményletöltés, hibakezelés és helyreállítás.
5. Automatizált folyamatellenőrzés, CI, biztonsági vizsgálatok és SBOM.
6. Telepítés, megfigyelhetőség, rollback és kipróbált helyreállítás.

Valódi hozzáférési titkot ne tegyél a Gitbe. A helyi konfigurációs értékekhez használd a `.env.example` fájlt mintaként.
