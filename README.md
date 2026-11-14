# PDF ↔ DOCX konverter

Egy helyben futtatható webalkalmazás alapja PDF és DOCX dokumentumok átalakításához. A projekt Python API-t, React felületet és PostgreSQL-adatbázist használ. A regisztráció és bejelentkezés elkészült; a konverziós motor és a tartós konverziós feladatkezelés következő fejlesztési lépés.

## Indítás

Szükséges: Docker és Docker Compose.

```sh
cp .env.example .env
docker compose up --build
```

- React felület: <http://localhost:5173>
- Kezdőlap és munkafelület: <http://localhost:5173/>
- Bejelentkezés/regisztráció: <http://localhost:5173/auth>
- Munkafelület belépési útvonal: <http://localhost:5173/auth/workspace>
- Profil: <http://localhost:5173/profile>
- Régi munkafelület-hivatkozás: <http://localhost:5173/converter>
- API dokumentáció: <http://localhost:8000/docs>
- API állapot: <http://localhost:8000/api/health>
- API és adatbázis állapota: <http://localhost:8000/api/health/ready>

Leállítás: `docker compose down`. A PostgreSQL-adatbázis a `postgres-data` nevű Docker volume-ban marad meg. Az adatbázis-migráció a backend indulásakor automatikusan lefut.

## Hitelesítés

- `POST /api/auth/register` — regisztráció `email` és legalább 8 karakteres `password` mezővel; access tokent ad vissza és refresh cookie-t állít be.
- `POST /api/auth/login` — bejelentkezés ugyanilyen JSON mezőkkel; új refresh sessiont indít.
- `POST /api/auth/refresh` — refresh cookie cseréje és új access token kiadása.
- `POST /api/auth/logout` — az aktuális refresh session visszavonása és a cookie törlése.
- `GET /api/auth/me` — bejelentkezett felhasználó adatainak lekérése `Authorization: Bearer <token>` fejléccel.

A jelszavak Argon2 hashként, a refresh tokenek SHA-256 hashként kerülnek a PostgreSQL-adatbázisba. A refresh token HttpOnly, SameSite=Lax cookie-ban van; minden frissítéskor új tokenre cserélődik, újrafelhasználáskor az adott session család visszavonódik. Az access token alapértelmezésben 15 percig, a refresh token legfeljebb 30 napig érvényes. Éles HTTPS környezetben állítsd a `REFRESH_COOKIE_SECURE=true` értéket. A tokenek aláírókulcsát és a PostgreSQL helyi jelszavát a `.env` fájl tartalmazza; a verziókezelt `.env.example` csak helyi fejlesztési mintát ad, valódi titkot ne tegyél a Gitbe.

## Szerkezet

- `backend/` — FastAPI API
- `frontend/` — React + TypeScript + Vite
- `compose.yaml` — helyi fejlesztői környezet

A kezdőlap és a konverziós munkafelület egy oldalon van; az input helyén a „Fejlesztés alatt” felirat látszik. A kezdőlap bejelentkezés nélkül is megnyitható, a profil bejelentkezést igényel. A `/auth/workspace` útvonal a munkafelületre belépéshez használható, a `/converter` útvonal pedig a főoldali munkafelülethez irányít. Docker Compose induláskor telepíti a frontend csomagjait a JSX-típusok frissítése érdekében.

## Következő fejlesztési lépések

1. Automatizált hitelesítési ellenőrzések és CI.
2. Fájlfeltöltés, méret- és formátumellenőrzés.
3. Konverziós feladatok és állapotuk tartós tárolása.
4. PDF → DOCX és DOCX → PDF feldolgozás, majd eredményletöltés.
5. Hibakezelés, újrapróbálás és kipróbált helyreállítás.
6. Biztonsági vizsgálatok, SBOM, megfigyelhetőség és rollback.

Valódi hozzáférési titkot ne tegyél a Gitbe. A helyi konfigurációs értékekhez használd a `.env.example` fájlt mintaként.
