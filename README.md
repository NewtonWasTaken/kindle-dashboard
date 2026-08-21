# 📱 Kindle Dashboard

Sleek, moderní a úsporný dashboard určený pro e-ink displeje (např. Kindle 10th generation v režimu na šířku / landscape 800×600). Renderování probíhá na serveru (např. Raspberry Pi) do 1bit/grayscale PNG s kompletní podporou české diakritiky a Kindle si pouze stahuje hotový obrázek.

---

## ✨ Hlavní Funkce

* 🐳 **Monitorování Docker Kontejnery (2-sloupcový grid):**
  * Zobrazuje služby ve střídmých kartičkách ve 2 sloupcích.
  * **Skutečné ikony služeb:** Automatické kešování a načítání originálních ikon z CDN (`dashboard-icons`) nebo přímo z webových favikon (`jangraffe.cz`, `skautitvarozna`, `pi-hole`, `immich`, `jellyfin`, `seafile`, `radicale` atd.).
  * **Dynamické auto-škálování písma:** Dlouhé názvy kontejnerů i verze se automaticky zmenší tak, aby se kompletně vešly do kartičky bez oříznutí.
  * **Svislé vycentrování:** Pokud služba nemá štítek verze, název se automaticky vycentruje na střed kartičky.
  * **Detekce verze:** Automatická detekce reálných verzí služeb z OCI labelů nebo proměnných prostředí.
  * **Stavové ikony:**
    * ❤️ **Srdíčko (`♥`):** Běží a healthcheck hlásí `healthy`.
    * **Puntík (`●`):** Běží (bez explicitního healthchecku).
    * ✕ **Křížek (`✕`):** Vypnutý / zastavený kontejner z `WATCHED_CONTAINERS` zůstává v seznamu s ikonou křížku.

* 📅 **Kalendář a Úkoly (Radicale CalDAV):**
  * **Vícedenní akce:** Vícedenní události (např. 3denní tábor) se přehledně zobrazují pod všemi dny, které zasahují.
  * **Filtrování:** Nastavitelné filtrování kalendářů pro události (`WATCHED_CALENDARS`) i úkoly (`WATCHED_TASK_CALENDARS`).
  * **Řazení úkolů:** Úkoly jsou seřazeny od nejbližšího termínu splnění po nejvzdálenější (úkoly bez termínu na konci).

* ⛅ **Počasí a Velké Hodiny:**
  * Výchozí pozice nastavena na **Prahu** (`50.0755`, `14.4378`).
  * Zvětšená předpověď počasí vpravo nahoře (48px teplota + 44px ikona) odpovídající velikosti hodin (64px).
  * **Časové pásmo:** Plná podpora pražského času (`Europe/Prague` / CEST) pomocí `ZoneInfo`.

* 🔄 **Pre-rotace obrázku pro Kindle:**
  * Možnost automatické rotace vygenerovaného PNG (`ROTATE_DEG=270` nebo `90`), aby se obrázek vytvořený na šířku (800×600) na hardwarovém displeji Kindlu zobrazil přesně přes celou obrazovku.

* 🔋 **Skript pro Kindle & KUAL Rozšíření:**
  * Podpora dvou režimů: **Live (30s refresh)** při napájení a **Battery (15min deep sleep)** pro výdrž na baterii.
  * KUAL menu nabídka se 3 tlačítky (*Live*, *Baterie*, *Zastavit Dashboard*).
  * Skrytí systémové lišty Kindlu přes `hideStatusBar 1` bez nutnosti zabíjení systémového prostředí.

---

## 🏗 Architektura

Tento projekt využívá architekturu **„server renders image, kindle fetches“**:
1. Server běží v Dockeru na vašem serveru / Raspberry Pi a v pravidelných intervalech (nebo na vyžádání) renderuje Pillow PNG obrázek.
2. Jailbreaknutý Kindle spouští lehký shell skript (`kindle/run.sh`), který stáhne vygenerované PNG a zobrazí ho na e-ink displeji pomocí `eips` nebo `FBInk`.

---

## 📋 Požadavky

* Docker a Docker Compose na hostitelském serveru
* Jailbreaknutý Kindle (pro spuštění skriptu přes KUAL / SSH)
* Radicale CalDAV server pro kalendář a úkoly (volitelné)

---

## 🚀 Rychlý Start (Server)

1. Naklonujte repozitář na server:
   ```bash
   git clone https://github.com/NewtonWasTaken/kindle-dashboard.git
   cd kindle-dashboard
   ```

2. Vytvořte a upravte konfiguraci `.env`:
   ```bash
   cp .env.example .env
   nano .env
   ```

3. Spusťte kontejner:
   ```bash
   docker compose up -d --build
   ```

4. Náhled vygenerovaného dashboardu otevřete v prohlížeči: `http://<IP-SERVERU>:5000/`

---

## ⚙️ Konfigurace (`.env`)

| Proměnná | Popis | Výchozí hodnota |
| -------- | ----- | --------------- |
| `WEATHER_LAT` | Zeměpisná šířka pro počasí (Praha) | `50.0755` |
| `WEATHER_LON` | Zeměpisná délka pro počasí (Praha) | `14.4378` |
| `RADICALE_URL` | URL pro Radicale CalDAV server | `http://radicale:5232/user/` |
| `RADICALE_USER` | Uživatel CalDAV | `user` |
| `RADICALE_PASS` | Heslo CalDAV | `password` |
| `WATCHED_CALENDARS` | Názvy kalendářů akcí (odělené čárkou) | `Osobní,Práce` |
| `WATCHED_TASK_CALENDARS` | Názvy kalendářů úkolů | `Úkoly` |
| `WATCHED_CONTAINERS` | Seznam sledovaných Docker kontejnerů | `immich,jellyfin,radicale,pihole,seadrive,hugo,sonarr,radarr` |
| `SCREEN_WIDTH` | Šířka rozvržení dashboardu | `800` |
| `SCREEN_HEIGHT` | Výška rozvržení dashboardu | `600` |
| `ROTATE_DEG` | Úhel rotace PNG obrázku pro Kindle (`0`, `90`, `180`, `270`) | `270` |
| `TZ` | Časové pásmo pro hodiny a události | `Europe/Prague` |
| `REFRESH_INTERVAL` | Interval kešování na serveru (sekundy) | `300` |
| `PORT` | Port Flask serveru | `5000` |

---

## 📱 Nastavení na Kindlu

### 1. Zkopírování skriptu a KUAL rozšíření
1. Připojte Kindle přes USB kabel k počítači.
2. Zkopírujte skript `kindle/run.sh` do složky **`/mnt/us/dashboard/run.sh`**.
3. Ve skriptu `run.sh` zkontrolujte číselnou IP adresu vašeho serveru:
   ```sh
   SERVER_URL="http://192.168.1.17:5000/dashboard.png"
   ```
4. Zkopírujte složku `kindle/extensions/dashboard` do složky **`/mnt/us/extensions/dashboard/`** na Kindlu:
   * `/mnt/us/extensions/dashboard/config.xml`
   * `/mnt/us/extensions/dashboard/menu.json`

### 2. Spuštění z KUALu
Otevřete aplikaci **KUAL** na Kindlu. V nabídce uvidíte rozbalovací položku **Kindle Dashboard**:
* **Spustit: Live (30s refresh):** Pro Kindle připojený na nabíječku.
* **Spustit: Baterie (15m refresh):** Pro běh na baterii s využitím RTC deep sleep.
* **Zastavit Dashboard:** Okamžitě ukončí skript, obnoví zamykání obrazovky i systémovou lištu a vrátí vás na domovskou obrazovku Kindlu.

---

## 🔌 API Endpointy

| Endpoint | Popis |
| -------- | ----- |
| `GET /` | Webová stránka s živým náhledem a metadaty serveru |
| `GET /dashboard.png` | Vygenerovaný 1bit/grayscale PNG obrázek pro Kindle |
| `GET /refresh` | Vynutí okamžité vygenerování nového obrázku bez čekání na keš |
| `GET /api/status` | JSON odpověď se stavem kontejnerů, počasí a kalendářů |

---

## 📄 Licence
Tento projekt je licencován pod MIT licencí.
