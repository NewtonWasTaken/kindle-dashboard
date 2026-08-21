#!/bin/sh
# ============================================================================
#  Kindle Dashboard — Fetch & Display Script
#  Umístit na Kindle: /mnt/us/dashboard/run.sh
# ============================================================================
#
#  DVA REŽIMY:
#    sh /mnt/us/dashboard/run.sh live      ← 30s refresh, Wi-Fi stále zapnutá
#    sh /mnt/us/dashboard/run.sh battery   ← 15min refresh, deep sleep
#
#  Bez argumentu se spustí režim "live".
#

# ---------- Konfigurace ----------
SERVER_URL="http://192.168.1.100:5000/dashboard.png"   # ← IP tvého RPi4
IMG_PATH="/tmp/dashboard.png"

LIVE_INTERVAL=30       # sekundy  (režim live)
BATTERY_INTERVAL=900   # sekundy  (režim battery — 15 min)
WIFI_TIMEOUT=30        # max čekání na Wi-Fi v battery režimu

# ---------- Režim ----------
MODE="${1:-live}"

# ---------- Pomocné funkce ----------
log() { echo "[$(date)] $1"; }

fetch_and_display() {
    if wget -q -O "$IMG_PATH" "$SERVER_URL" 2>/dev/null; then
        if command -v fbink >/dev/null 2>&1; then
            fbink -f -g "file=$IMG_PATH" -q
        else
            eips -g "$IMG_PATH"
        fi
        return 0
    fi
    return 1
}

wifi_on()  { lipc-set-prop com.lab126.wifid enable 1 2>/dev/null; }
wifi_off() { lipc-set-prop com.lab126.wifid enable 0 2>/dev/null; }

wait_for_wifi() {
    ELAPSED=0
    while [ "$ELAPSED" -lt "$WIFI_TIMEOUT" ]; do
        wget -q --spider "$SERVER_URL" 2>/dev/null && return 0
        sleep 2
        ELAPSED=$((ELAPSED + 2))
    done
    return 1
}

# ---------- Inicializace ----------
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

log "=== Kindle Dashboard ==="
log "Režim: $MODE"

# =====================================================================
#  LIVE REŽIM — 30s refresh, Wi-Fi stále zapnutá, bez deep sleep
#  Doporučeno: Kindle na nabíječce (baterie ~12-24h)
# =====================================================================
if [ "$MODE" = "live" ]; then
    log "Wi-Fi zapínám (zůstane zapnutá)..."
    wifi_on
    sleep 5

    while true; do
        fetch_and_display || log "Stažení selhalo"
        sleep "$LIVE_INTERVAL"
    done
fi

# =====================================================================
#  BATTERY REŽIM — 15min refresh, deep sleep, Wi-Fi se zapíná/vypíná
#  Baterie vydrží 3-8 týdnů
# =====================================================================
if [ "$MODE" = "battery" ]; then
    while true; do
        log "Wi-Fi zapínám..."
        wifi_on

        if wait_for_wifi; then
            log "Stahuji dashboard..."
            fetch_and_display || log "Stažení selhalo"
        else
            log "Wi-Fi timeout"
        fi

        log "Wi-Fi vypínám..."
        wifi_off

        log "Uspávám na ${BATTERY_INTERVAL}s..."
        if [ -e /dev/rtc1 ]; then
            rtcwake -d /dev/rtc1 -m no -s "$BATTERY_INTERVAL"
        else
            rtcwake -d /dev/rtc0 -m no -s "$BATTERY_INTERVAL"
        fi
        echo mem > /sys/power/state

        log "Probouzím se."
    done
fi

log "Neznámý režim: $MODE (použij 'live' nebo 'battery')"
exit 1
