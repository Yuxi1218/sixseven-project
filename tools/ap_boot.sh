#!/usr/bin/env bash
# 六七 熱點（AirCraft67Team）開機自動啟動
# 由 systemd unit sixseven-ap.service 於開機呼叫。
# 幂等：已在該 AP 上就直接成功退出；等 NetworkManager 與 wifi 裝置就緒後再起。
set -u

AP_NAME="${AP_NAME:-AirCraft67Team}"
AP_DEV="${AP_DEV:-wlP1p1s0}"
AP_RETRIES="${AP_RETRIES:-8}"
AP_SLEEP="${AP_SLEEP:-3}"

log() { echo "[ap_boot] $*"; }

# 1) 等 NetworkManager 可用（最多 30s）
for _ in $(seq 1 30); do
    nmcli general status >/dev/null 2>&1 && break
    sleep 1
done
if ! nmcli general status >/dev/null 2>&1; then
    log "NetworkManager 未就緒，放棄"
    exit 1
fi

# 2) 等 wifi 裝置出現（rtl8822ce SDIO 需數秒；最多 30s）
for _ in $(seq 1 30); do
    nmcli -t -f DEVICE device status 2>/dev/null | grep -q "^${AP_DEV}:" && break
    sleep 1
done

# 3) profile 必須存在（新機請先跑 tools/setup_env.sh 建立）
if ! nmcli -t -f NAME connection show 2>/dev/null | grep -Fxq "$AP_NAME"; then
    log "找不到連線 profile『$AP_NAME』，請先執行 tools/setup_env.sh"
    exit 1
fi

# 4) 已在該 AP 上？（幂等）
active_dev=$(nmcli -t -f NAME,DEVICE connection show --active 2>/dev/null \
    | grep -F "^${AP_NAME}:" | cut -d: -f2)
if [ -n "$active_dev" ] && [ "$active_dev" != "--" ]; then
    log "已啟用：$AP_NAME on $active_dev"
    exit 0
fi

# 5) 重試啟動 AP
for i in $(seq 1 "$AP_RETRIES"); do
    log "啟動 $AP_NAME（第 $i/$AP_RETRIES 次）…"
    if nmcli connection up "$AP_NAME" >/dev/null 2>&1; then
        ipaddr=$(ip -4 -o addr show "$AP_DEV" 2>/dev/null \
            | awk '{print $4}' | cut -d/ -f1 | head -1)
        if [ -n "$ipaddr" ]; then
            log "OK：$AP_NAME 已上線，$AP_DEV = $ipaddr"
            exit 0
        fi
        # 曾經遇過 activated 但介面沒拿到 IPv4：強制 down 後重試，避免假成功
        log "已 activated 但 $AP_DEV 無 IPv4，強制 down 後重試…"
        nmcli connection down "$AP_NAME" >/dev/null 2>&1 || true
    fi
    sleep "$AP_SLEEP"
done

log "啟動 $AP_NAME 失敗（重試 $AP_RETRIES 次）"
exit 1
