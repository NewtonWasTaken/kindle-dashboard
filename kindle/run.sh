#!/bin/sh
# ============================================================================
#  Kindle Dashboard — Fetch & Display Script
#  Umístit na Kindle: /mnt/us/dashboard/run.sh
# ============================================================================

SERVER_URL="http://192.168.1.47:5000/dashboard.png"
IMG_PATH="/tmp/dashboard.png"
LOG_FILE="/tmp/dashboard.log"
PID_FILE="/tmp/dashboard.pid"

LIVE_INTERVAL=30       # sekundy  (režim live)
BATTERY_INTERVAL=900   # sekundy  (režim battery — 15 min)
WIFI_TIMEOUT=30        # max čekání na Wi-Fi v battery režimu

MODE="${1:-live}"

log() {
    echo "[$(date)] $1" >> "$LOG_FILE"
}

# ----------------------------------------------------------------------------
# REŽIM STOP — Ukončení běhu skriptu a obnovení rozhraní Kindlu
# ----------------------------------------------------------------------------
if [ "$MODE" = "stop" ]; then
    log "Zastavuji Kindle Dashboard..."
    if [ -f "$PID_FILE" ]; then
        OLD_PID=$(cat "$PID_FILE")
        if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
            kill -9 "$OLD_PID" 2>/dev/null
        fi
        rm -f "$PID_FILE"
    fi
    pkill -f "run.sh" 2>/dev/null
    # Obnovení systémové lišty, hodin a zamykání obrazovky
    lipc-set-prop com.lab126.statusbar hideStatusBar 0 2>/dev/null
    lipc-set-prop com.lab126.statusbar clockVisible 1 2>/dev/null
    lipc-set-prop com.lab126.pillow disableHeader 0 2>/dev/null
    lipc-set-prop com.lab126.pillow suppressHeader 0 2>/dev/null
    lipc-set-prop com.lab126.powerd preventScreenSaver 0 2>/dev/null
    # Návrat na domovskou obrazovku Kindlu
    lipc-set-prop com.lab126.appmgrd start app://com.lab126.booklet.home 2>/dev/null
    exit 0
fi

# Zabít případnou předchozí instanci
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill -9 "$OLD_PID" 2>/dev/null
    fi
    rm -f "$PID_FILE"
fi

echo $$ > "$PID_FILE"

fetch_and_display() {
    log "Stahuji z $SERVER_URL ..."
    if wget -q -O "$IMG_PATH" "$SERVER_URL" 2>/dev/null; then
        log "Stažení úspěšné, vykresluji na e-ink..."
        if command -v fbink >/dev/null 2>&1; then
            fbink -f -g "file=$IMG_PATH" -q
        else
            eips -c
            eips -g "$IMG_PATH"
        fi
        return 0
    else
        log "CHYBA: Wget selhal pro URL $SERVER_URL"
        return 1
    fi
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

# Skryje horní lištu, systémové hodiny i Pillow záhlaví, ale PONECHÁ systém běhat na pozadí
lipc-set-prop com.lab126.statusbar hideStatusBar 1 2>/dev/null
lipc-set-prop com.lab126.statusbar clockVisible 0 2>/dev/null
lipc-set-prop com.lab126.pillow disableHeader 1 2>/dev/null
lipc-set-prop com.lab126.pillow suppressHeader 1 2>/dev/null
lipc-set-prop com.lab126.powerd preventScreenSaver 1 2>/dev/null

log "=== Spouštím Kindle Dashboard (Režim: $MODE) ==="

if [ "$MODE" = "live" ]; then
    wifi_on
    sleep 3
    while true; do
        fetch_and_display
        sleep "$LIVE_INTERVAL"
    done
fi

if [ "$MODE" = "battery" ]; then
    while true; do
        wifi_on
        if wait_for_wifi; then
            fetch_and_display
        else
            log "Wi-Fi timeout"
        fi
        wifi_off
        if [ -e /dev/rtc1 ]; then
            rtcwake -d /dev/rtc1 -m no -s "$BATTERY_INTERVAL"
        else
            rtcwake -d /dev/rtc0 -m no -s "$BATTERY_INTERVAL"
        fi
        echo mem > /sys/power/state
    done
fi
