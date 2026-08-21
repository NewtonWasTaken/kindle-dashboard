# 📱 Kindle Dashboard

Dashboard pro jailbreaknutý Kindle zobrazující stav Docker kontejnerů, počasí, kalendář a úkoly. Renderování probíhá na serveru (např. Raspberry Pi) a Kindle si pouze stahuje hotový obrázek.

## ✨ Funkce
- 🐳 **Stav Docker kontejnerů**: Zobrazuje, zda vybrané kontejnery běží.
- ⛅ **Počasí**: Aktuální počasí pro zadanou lokaci.
- 📅 **Kalendář**: Načítá události z Radicale CalDAV serveru.
- ✅ **Úkoly**: Zobrazuje aktuální úkoly.
- 🔋 **Úspora baterie**: Kindle se probudí, stáhne obrázek, aktualizuje displej a znovu usne.

## 🏗 Architektura
Tento projekt využívá architekturu "server-renders-image, kindle-fetches". 
Server běží v Dockeru (ideálně na Raspberry Pi), načítá data z různých zdrojů a renderuje je do PNG obrázku optimalizovaného pro e-ink displej (včetně české diakritiky).
Jailbreaknutý Kindle používá jednoduchý shell skript s cronem, který pravidelně probouzí zařízení z hlubokého spánku (RTC wake), zapne Wi-Fi, stáhne obrázek, překreslí displej a zařízení zase uspí pro maximální výdrž baterie.

## 📋 Požadavky
- Docker a Docker Compose na hostitelském serveru
- Jailbreaknutý Kindle (pro běh shell skriptů, např. přes KUAL/SSH)
- Radicale CalDAV server pro kalendář a úkoly
- Nástroj pro překreslení e-ink displeje (FBInk nebo integrovaný eips)

## 🚀 Instalace a spuštění

1. Naklonujte repozitář na váš server:
```bash
git clone <repo_url> /home/jgraf/kindle-dashboard
cd /home/jgraf/kindle-dashboard
```

2. Zkopírujte ukázkovou konfiguraci a upravte ji:
```bash
cp .env.example .env
nano .env
```

3. Spusťte přes Docker Compose:
```bash
docker-compose up -d --build
```

4. Pro ověření přejděte na adresu: `http://<ip-vaseho-serveru>:5000/`

## ⚙️ Konfigurace (.env)

| Proměnná | Popis | Výchozí hodnota |
| -------- | ----- | --------------- |
| `WEATHER_LAT` | Zeměpisná šířka pro počasí | 49.1847 |
| `WEATHER_LON` | Zeměpisná délka pro počasí | 16.7064 |
| `RADICALE_URL` | URL na váš Radicale CalDAV | http://radicale:5232/user/ |
| `RADICALE_USER` | Uživatel pro Radicale | user |
| `RADICALE_PASS` | Heslo pro Radicale | password |
| `WATCHED_CONTAINERS` | Seznam kontejnerů oddělený čárkou | immich,jellyfin... |
| `SCREEN_WIDTH` | Šířka displeje (podle modelu) | 600 |
| `SCREEN_HEIGHT` | Výška displeje (podle modelu) | 800 |
| `REFRESH_INTERVAL` | Jak často se načítají nová data | 300 (sekundy) |
| `PORT` | Port, na kterém aplikace poběží | 5000 |

## 📖 Nastavení Kindle

1. Připojte Kindle přes USB nebo SSH.
2. Zkopírujte skript `kindle/run.sh` do umístění (např. `/mnt/us/dashboard/run.sh`).
3. Upravte `SERVER_URL` ve skriptu na IP adresu vašeho serveru.
4. Doporučuje se instalace [FBInk](https://github.com/NiLuJe/FBInk) pro rychlé překreslení, v základu se použije `eips`.
5. Spusťte skript přes SSH (`sh /mnt/us/dashboard/run.sh`) nebo jej zaintegrujte do KUAL, či vytvořte cron/init skript.

## 🔌 API Endpointy

| Endpoint | Popis |
| -------- | ----- |
| `GET /` | Webová stránka pro náhled s metadaty |
| `GET /dashboard.png` | Samotný vygenerovaný obrázek pro Kindle |
| `GET /refresh` | Manuálně vynutí okamžité vygenerování nového obrázku |
| `GET /api/status` | JSON odpověď se stavem serveru a připojených služeb |

## 📄 Licence
Tento projekt je licencován pod MIT licencí.
