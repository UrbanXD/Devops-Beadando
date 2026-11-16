# Megfigyelhetőség

A helyi fejlesztői környezet Prometheusszal gyűjti az API metrikáit, Grafana dashboardon mutatja őket, az alkalmazás pedig JSON formátumú kérés- és konverziós eseményeket ír a konténer naplójába.

## Indítás

```sh
docker compose --profile observability up --build
```

- Grafana dashboard: <http://127.0.0.1:13111/d/converter-observability>
- Prometheus target állapot: <http://127.0.0.1:19111/targets>
- Prometheus riasztások: <http://127.0.0.1:19111/alerts>
- API metrikák: <http://localhost:8000/metrics/>
- API eseménynaplók: `docker compose logs -f api`

A Grafana névtelen, csak olvasási hozzáféréssel indul, és a hoston csak `127.0.0.1` címen érhető el. Ezt a beállítást ne használd nyilvános hálózaton. A Grafana és Prometheus adatai Docker volume-ban maradnak meg. Leállítás: `docker compose --profile observability down`.

## Mért adatok

- `converter_http_requests_total{method,route,status}` — regisztrált API útvonalak befejezett kérései. A healthcheck és a `/metrics` lekérései nem kerülnek bele.
- `converter_http_request_duration_seconds` — a kérés feldolgozási ideje a válasz elkészítéséig. Nem tartalmazza a fájl teljes kliensoldali letöltési idejét.
- `converter_conversion_attempts_total{direction}` — érvényes PDF/DOCX bemenet után elindított konverziók száma.
- `converter_conversion_jobs_total{direction,result}` — az érvényes PDF/DOCX bemenet után befejezett konverzió eredménye. A hibás formátumú, üres vagy túl nagy feltöltés nem konverziós kísérlet.
- `converter_conversion_duration_seconds{direction,result}` — a konverzió és az eredmény előkészítésének ideje. Bejelentkezett felhasználónál az előzmény mentése is beletartozik.
- `up{job="converter-api"}` — Prometheus eléri-e az API metrikavégpontját. Ez önmagában nem bizonyít sikeres konverziót.

A metrikák címkéi korlátozottak: az útvonal a FastAPI sablonja, a konverziós irány és eredmény rögzített értékkészletű. Kérésazonosító, fájlnév, e-mail-cím, token és nyers URL nem kerül Prometheus-címkébe.

Az alkalmazás JSON naplói UTC-időpontot, eseményt, útvonalsablont, HTTP-státuszt vagy konverziós eredményt, futási időt és kérésazonosítót tartalmaznak. A kérésazonosító az `X-Request-ID` válaszfejlécben is megjelenik. A Docker naplója a részletes események helye; a Prometheus metrikaadatokat nem használjuk az egyedi kérések történetének visszakeresésére.

## SLI és SLO

**Konverziós SLI:** a 120 másodpercen belül sikeres kimenetet előkészítő érvényes konverziók aránya az összes érvényes konverziós kísérletből.

**Konverziós SLO:** legalább 99% sikeres kimenet gördülő 7 nap alatt. A hibás feltöltések és az elutasított bemenetek kimaradnak a nevezőből; a konverterhiba, időtúllépés, eredményfájl-hiba és bejelentkezett felhasználónál az előzmény mentési hibája sikertelen kísérlet.

Az API 5xx hibaaránya külön diagnosztikai mutató a regisztrált API-útvonalakra. A 4xx válasz sikeres kéréskezelésnek számít, mert az API visszautasította a hibás vagy jogosulatlan kérést. A healthcheck és a metrikavégpont egyik üzleti arányban sem szerepel.

A dashboard SLI panelje nem mutat 100%-ot forgalom nélkül: ilyenkor nincs mérhető nevező. A Prometheus 15 napnyi mintát tart meg, hogy legyen elegendő adat a gördülő 7 napos értékeléshez. Az első hét során az SLO még nem teljes időablakon alapul.

Az alkalmazás számlálói memóriában vannak, ezért az API újraindításakor nullázódnak. Prometheus a begyűjtött mintákból folytatja a számítást; az újraindítás előtt még le nem scrape-elt események nem állíthatók vissza.

A Prometheus `ConversionSLOHighBurnRate` riasztása akkor aktiválódik, ha legalább tíz konverzió mellett az 5 perces rossz kimeneti arány tartósan meghaladja a 10%-ot. Ez a 99%-os cél 1%-os hibakeretéhez képest tízszeres burn rate. A `PrometheusScrapeFailed` jelzés a metrikagyűjtési hibát mutatja; ez önmagában nem bizonyít felhasználói API-hibát. A riasztások a Prometheus felületén láthatók, külső értesítési csatorna nincs beállítva.

## Napló és metrika ellenőrzése

Egy sikeres és egy hibás feltöltés után a Grafana dashboardon megjelennek a kérés-, válaszidő- és konverziós adatok. A megfelelő események a `docker compose logs api` kimenetében kereshetők a `request_id`, `direction` és `result` mezők alapján. A Prometheus target állapota a gyűjtés sikerét jelzi; üzleti eredményt a konverziós SLI mutat.

### Kapcsolódó konfigurációk

- `backend/app/observability.py` — metrikák és JSON naplóesemények.
- `observability/prometheus.yml` — scrape beállítás.
- `observability/alerts.yml` — konverziós SLO riasztás.
- `observability/dashboards/converter.json` — verziózott dashboard.
- `observability/grafana/provisioning/` — automatikusan betöltött adatforrás és dashboard.

### Manuális teszteléshez hibás pdf generálás
```sh
    printf '%s\n' '%PDF-1.4' 'ez nem valódi PDF' > hibas.pdf
    ls -l hibas.pdf
   ```