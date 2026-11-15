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

## Kubernetes fejlesztői és staging környezet

Kind-alapú, két elkülönített namespace-es telepítés, verziózott image-ek és Helm-revízióból történő visszaállítás: [DEPLOYMENT.md](DEPLOYMENT.md).

## Automatizált ellenőrzések

Az API-tesztek külön, memóriabeli SQLite-adatbázist használnak.

GitHub Actions minden pushnál és pull requestnél lefuttatja a backendteszteket és a frontend buildet, ellenőrzi a titkokat és a függőségek ismert sérülékenységeit, valamint megvizsgálja a Docker image-eket. A Trivy a munkafát, a TruffleHog a teljes Git-előzményt ellenőrzi. A konténer image-ek egyszer épülnek fel, majd artifactként jutnak el a külön vizsgálati jobba. A konténer scan jelentése a forrás commitot, a futás azonosítóját, a Trivy verzióját és a sérülékenységi adatbázis adatait is tartalmazza. A `Security gate` a jelentések alapján `PASS`, `BLOCK` vagy `ERROR` döntést hoz; hiányzó vagy hibás jelentés `ERROR`. A javítható HIGH/CRITICAL image-sebezhetőség, a HIGH/CRITICAL npm-sebezhetőség, bármely ismert Python-sérülékenység vagy titoktalálat `BLOCK`. A javítás nélküli HIGH/CRITICAL és UNKNOWN image-találatok a riportban maradnak, de nem blokkolják a gate-et; javítható UNKNOWN találat `ERROR`. A push során készült SBOM-okat Cosign keyless aláírás hitelesíti GitHub OIDC-identitással, a kapu pedig ellenőrzi az aláírást és a workflow-identitást. Pull requestnél az SBOM elkészül, aláírás push során készül. A frontend buildje és a vizsgálati jelentések CI artifactként letölthetők. A build és a vizsgálati jelentések 14 napig, a vizsgálatra átadott image-ek 3 napig, az SBOM-ok 30 napig érhetők el. A workflow külső GitHub Actionjei teljes commit SHA alapján vannak rögzítve.

**Helyi CI-ellenőrzések:** a jelentések a `reports/` mappába kerülnek. A kapu a vizsgálati jelentéseket együtt értékeli, ezért az ellenőrzések futtatási sorrendje:

- Munkafa titokvizsgálata: `bash scripts/scan-worktree-secrets.sh`.
- Git-előzmények titokvizsgálata: `bash scripts/scan-git-history-secrets.sh`.
- Python-függőségek vizsgálata: `bash scripts/audit-python-dependencies.sh`.
- Frontend-függőségek vizsgálata: `bash scripts/audit-frontend-dependencies.sh`.
- Docker image-ek buildelése és artifact készítése: `bash scripts/build-container-artifact.sh`.
- Image-ek ellenőrzése és SBOM készítése: `bash scripts/scan-container-images.sh reports reports`.
- A jelentések policy szerinti kiértékelése: `bash scripts/security-gate.sh reports reports`.

Docker-ellenőrzésekhez működő Docker és internetkapcsolat szükséges. A Python audit a `backend/requirements-dev.txt` fájlban lévő `pip-audit` csomagot használja, ezért annak telepítése is szükséges a `.venv`-be. A frontend audit npm-et igényel. A `reports/converter-images.tar.gz` az image artifact, a hozzá tartozó `.sha256` fájl az ellenőrzőösszeg. A titokvizsgálati jelentés a találat helyét és típusát tartalmazza, titokértéket nem.

**SBOM-aláírás:** a `scripts/sign-sboms.sh` Cosign keyless aláírást készít. A CI-ban GitHub OIDC-token szükséges hozzá, ezért külön, csak push eseménynél futó jobban készül. Az aláírási bundle külön CI artifact, a kapu pedig ellenőrzi az SBOM és az aláíró workflow azonosságát. A merge tiltásához a GitHub branch protectionben a `Security gate` ellenőrzés required status checkként beállítandó.

**Git-előzmények scan próbája:** `bash scripts/test-git-history-secrets.sh`. A script ideiglenes Git-tárolóban mesterséges tokent ad hozzá, törli, majd ellenőrzi, hogy a history scan megtalálja-e.

A helyi `.env` fájl nem kerülhet a Gitbe. Az `.env.example` kizárólag helyi fejlesztési minta, éles hitelesítő adatot nem tartalmazhat. A CI jelenleg nem igényel valódi hozzáférési titkot. Ha később szükség lesz rá, azt a GitHub Actions titokkezelőjében kell tárolni, nem a workflow fájlban.

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
- `DELETE /api/conversions/history/{conversion_id}` — egy saját előzmény és eredményfájl törlése.
- `DELETE /api/conversions/history` — az összes saját előzmény és eredményfájl törlése.

A PDF → DOCX átalakítást a `pdf2docx`, a DOCX → PDF átalakítást a Docker-képbe telepített LibreOffice végzi. A LibreOffice helyi futtatásához külön telepítése szükséges.

A jelszavak Argon2 hashként, a refresh tokenek SHA-256 hashként kerülnek az adatbázisba. A refresh token HttpOnly, SameSite=Lax cookie-ban van, és minden frissítéskor új tokenre cserélődik. Az access token alapértelmezett élettartama 15 perc, a refresh tokené legfeljebb 30 nap. Éles HTTPS-környezetben a `REFRESH_COOKIE_SECURE=true` beállítás szükséges.

## Projektfájlok

- `backend/` — FastAPI API, adatmodellek és Alembic-migrációk.
- `frontend/` — React + TypeScript + Vite felület.
- `compose.yaml` — helyi fejlesztői környezet.
- `deploy/helm/converter/` — Kubernetes Helm chart.
- `DEPLOYMENT.md` — fejlesztői/staging telepítés és visszaállítás.
- `.env.example` — helyi konfiguráció mintája.

Valódi hozzáférési titok nem kerülhet a Gitbe.
