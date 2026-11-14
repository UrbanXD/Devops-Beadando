A hallgató egy nem triviális, de egy fő által megvalósítható rendszerhez alakít ki reprodukálható fejlesztési és üzemeltetési folyamatot. A rendszernek rendelkeznie kell felhasználói vagy API-belépési ponttal, tartós adattárolással és legalább egy érdemi kiegészítő feldolgozással vagy integrációval. Legalább három felhasználói folyamatot kell dokumentálni, köztük egy hiba- vagy helyreállítási útvonalat. Egy statikus oldal, változtatás nélkül átvett tutorial vagy kizárólag alapvető CRUD-műveleteket megvalósító alkalmazás önmagában nem elegendő.


A projekt értékelése:

Terület
	

Pont

Egy főre méretezett, érdemi rendszer és indokolt architektúra
	

5

Reprodukálható helyi környezet és áttekinthető repository
	

5

Automatizált tesztek és folyamatos integráció
	

9

Artifactkezelés, biztonsági vizsgálat, SBOM és titokkezelés
	

7

Deklaratív telepítés, elkülönített környezetek, verzióváltás és visszaállítás
	

9

CD/GitOps: Gitben tárolt kívánt állapot és automatizált kiadáskezelés
	

5

IaC- és konfigurációkezelési döntések, reprodukálhatóság
	

5

Metrikák, naplózás, dashboard és SLI/SLO
	

7

Megbízhatósági és helyreállítási bizonyítékok
	

4

Az AI-támogatott munkafolyamat szakmai ellenőrzése
	

4

Összesen
	

60


Az értékelés nem a felhasznált eszközök számán alapul. A technológiai választásokat a rendszer igényeivel kell indokolni. Egy adott eszköz helyett alkalmazott alternatíva esetén dokumentálni kell, hogyan teljesül az elvárt képesség.

A beadás része a forráskód és a telepítési konfiguráció, a működést és reprodukciót bemutató README, az architektúra és a fontos döntések dokumentációja, az automatizált ellenőrzések bizonyítékai, a megfigyelhetőségi eredmények, egy kipróbált helyreállítási eljárás és az AI-használat rövid szakmai dokumentációja.

A projektből legalább 30 pontot kell elérni. Emellett kötelező, hogy a projekt tiszta környezetben reprodukálható legyen, ne tartalmazzon valódi hozzáférési titkot, és legalább egy felhasználói folyamat működését automatizált ellenőrzés igazolja.
