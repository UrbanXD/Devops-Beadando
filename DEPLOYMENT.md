# Kubernetes telepítés

A konverter helyi Kind-klaszteren futtatható külön fejlesztői és staging környezetben. A Helm chart leírja az alkalmazás, az adatbázis és a tárolók erőforrásait. A két környezet külön namespace-t és külön adatokat kap.

## Szükséges eszközök

- Docker
- Kind
- kubectl
- Helm 3
- OpenSSL
- Python 3

## Fejlesztői telepítés

A script létrehozza a `converter` nevű Kind-klasztert, ha még nem létezik. Meglévő klasztert újrahasznál, így nem kell kézzel ismét létrehozni. Az alapértelmezett kubectl context `kind-converter`.

```sh
IMAGE_TAG="dev-$(date -u +%Y%m%d%H%M%S)"
bash scripts/deploy-k8s.sh development "$IMAGE_TAG"
```

A telepítő egy menetben felépíti és betölti az image-eket, létrehozza a namespace-t és a titkokat, futtatja a Helm kiadást, majd ellenőrzi a podokat. Minden új buildhez új tag szükséges; létező taget a script nem épít fel újra.

Ha a Kind-klaszter neve eltér az alapértelmezettől, a név megadható a parancs végén:

```sh
bash scripts/deploy-k8s.sh development "$IMAGE_TAG" converter-stage
```

Eltérő Kubernetes context esetén a `KUBE_CONTEXT` változó adható meg, például: `KUBE_CONTEXT=kind-converter bash scripts/deploy-k8s.sh development "$IMAGE_TAG"`.

## Elérés és ellenőrzés

```sh
kubectl --context kind-converter -n converter-dev get pods,svc,pvc
kubectl --context kind-converter -n converter-dev port-forward svc/web 5173:80
```

A port-forward parancsot hagyd futni egy terminálban; a `curl` parancsok külön terminálból futnak:

```sh
curl --fail http://localhost:5173/
curl --fail http://localhost:5173/api/health/ready
```

A `ready` válasz az adatbázis-kapcsolatot is ellenőrzi.

## Staging kiadás

Ugyanaz az image-tag telepíthető stagingre. Így a kipróbált image jut tovább, új build nélkül:

```sh
bash scripts/deploy-k8s.sh staging "$IMAGE_TAG"
kubectl --context kind-converter -n converter-staging get pods,svc,pvc
```

Fejlesztői és staging környezetben külön PostgreSQL-adatbázis, fájltár és `converter-runtime` Secret jön létre. A Secret értékeit a script első telepítéskor véletlenszerűen előállítja, majd következő kiadáskor ugyanazokat használja újra. Az értékek nem kerülnek a Gitbe.

## Verzióváltás és visszaállítás

Új verzióhoz új taggel telepíts:

```sh
NEXT_IMAGE_TAG="check-2"
bash scripts/deploy-k8s.sh development "$NEXT_IMAGE_TAG"
```

A Helm kiadás revízióinak megtekintése és visszaállítása:

```sh
helm history converter --kube-context kind-converter -n converter-dev
bash scripts/deploy-k8s.sh rollback development 1
helm status converter --kube-context kind-converter -n converter-dev
```

A `1` helyére a `helm history` kimenetében látható korábbi, működő revízió száma kerül. Hibás telepítéskor a script megjeleníti a podállapotot, eseményeket és web pod naplóját.

A Helm a Kubernetes-erőforrások és image-verziók korábbi állapotát állítja vissza; az adatbázis-sémát, PostgreSQL-adatokat és konverziós fájlokat nem. Új adatbázis-migrációnál ezért előre- és visszafelé kompatibilis kiadási sorrend szükséges. A namespace törlése az ott tárolt adatokat is eltávolíthatja.

## Fájlok és döntések

- `deploy/helm/converter/` — API, web, PostgreSQL, PVC-k és ellenőrző probe-ok Helm chartja.
- `values-development.yaml`, `values-staging.yaml` — környezetenkénti tárolóméretek és image-beállítások.
- `scripts/deploy-k8s.sh` — klaszter, build, telepítés, titkok és rollback egy scriptben.

Az API környezetenként egy példánnyal fut, mert a konverziós fájltár `ReadWriteOnce` PVC-t használ. A Kubernetes namespace-ek elkülönítik az erőforrásokat, de önmagukban nem biztonsági határok. A refresh cookie HTTPS-beállítása csak TLS-es ingress vagy proxy bevezetése után kapcsolható be.
