#!/usr/bin/env bash
# ============================================================================
#  六七 (sixseven) 機翼損傷偵測系統 — 全新系統「一鍵」環境建置
# ----------------------------------------------------------------------------
#  適用：Jetson Orin Nano / JetPack 6.2 (L4T R36.4.7) / Ubuntu 22.04 / aarch64
#  用途：SD 卡壞了、換新卡重刷 JetPack 後，跑這一支把整台機器恢復到能跑。
#
#  用法：sudo bash tools/setup_env.sh [選項]
#     --with-engine   額外建置 TensorRT engine（約 5~10 分鐘，可讓推論 ~2.7x 快）
#     --skip-apt      跳過系統套件安裝
#     --skip-pip      跳過 Python 套件安裝
#     --skip-ollama   跳過 Ollama 安裝
#
#  流程（最後一步才是開熱點，因為熱點模式沒有對外網路）：
#     0 網路檢查 → 1 系統套件 → 2 Python 套件 → 3 libcudss → 4 Ollama
#     → 5 systemd 服務 → 6 埠號 sysctl → 7 sudoers/tmpfiles → 8 cron
#     → 9 HTTPS 憑證 → 10 (選)TRT engine → 11 啟動 WebUI → 12 開熱點(最後)
#
#  完成後：手機連 WiFi「AirCraft67Team」(密碼 67676767) → 瀏覽器輸入 10.42.0.1
#          （會自動跳轉 https://10.42.0.1）
# ============================================================================
set -uo pipefail

WITH_ENGINE=0
SKIP_APT=0
SKIP_PIP=0
SKIP_OLLAMA=0
for a in "$@"; do
    case "$a" in
        --with-engine) WITH_ENGINE=1 ;;
        --skip-apt)    SKIP_APT=1 ;;
        --skip-pip)    SKIP_PIP=1 ;;
        --skip-ollama) SKIP_OLLAMA=1 ;;
        -h|--help)     sed -n '1,30p' "$0"; exit 0 ;;
        *) echo "未知參數：$a（-h 看說明）" >&2; exit 2 ;;
    esac
done

# ---------- 基本路徑 / 參數 ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
WEBUI_DIR="$PROJECT_DIR/webUI_workspace"
SYSTEMD_SRC="$PROJECT_DIR/systemd"

TARGET_USER="${TARGET_USER:-sixseven}"
TARGET_HOME="$(getent passwd "$TARGET_USER" 2>/dev/null | cut -d: -f6)"
[ -z "$TARGET_HOME" ] && TARGET_HOME="/home/$TARGET_USER"

AP_SSID="${AP_SSID:-AirCraft67Team}"
AP_PASS="${AP_PASS:-67676767}"
AP_IP="${AP_IP:-10.42.0.1}"
AP_DEV="${AP_DEV:-$(iw dev 2>/dev/null | awk '/Interface/{print $2; exit}')}"
AP_DEV="${AP_DEV:-wlP1p1s0}"

JETSON_PIP_INDEX="${JETSON_PIP_INDEX:-https://pypi.jetson-ai-lab.io/jp6/cu126}"
OLLAMA_MODEL="${OLLAMA_MODEL:-gemma3:1b}"
CUDSS_DIR="$TARGET_HOME/.local/lib/python3.10/site-packages/nvidia/cu12/lib"

BOLD=$'\033[1m'; GRN=$'\033[32m'; YEL=$'\033[33m'; RED=$'\033[31m'; RST=$'\033[0m'
step(){ echo; echo "${BOLD}========== $* ==========${RST}"; }
ok(){   echo "  ${GRN}✓${RST} $*"; }
warn(){ echo "  ${YEL}!${RST} $*"; }
die(){  echo "${RED}✗ $*${RST}" >&2; exit 1; }
run_as(){ sudo -u "$TARGET_USER" -H env HOME="$TARGET_HOME" \
    PATH="$TARGET_HOME/.local/bin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin" "$@"; }
py(){ run_as python3 "$@"; }

# ---------- 前置檢查 ----------
[ "$(id -u)" -eq 0 ] || die "請用 sudo 執行：sudo bash tools/setup_env.sh"
[ "$(uname -m)" = "aarch64" ] || warn "非 aarch64（目前 $(uname -m)），Jetson 專用套件可能不相容"
[ -d "$WEBUI_DIR" ] || die "找不到 $WEBUI_DIR，請確認在專案目錄內執行"
id "$TARGET_USER" >/dev/null 2>&1 || die "找不到使用者 $TARGET_USER"

echo "${BOLD}六七系統環境建置${RST}"
echo "  專案：$PROJECT_DIR"
echo "  使用者：$TARGET_USER（$TARGET_HOME）"
echo "  WiFi 介面：$AP_DEV　熱點：$AP_SSID ($AP_IP)　選項：engine=$WITH_ENGINE"

# ============================================================================
step "0. 對外網路檢查"
# ============================================================================
net_ok(){ curl -fsS -m 8 -o /dev/null https://pypi.org/simple/ 2>/dev/null; }
if net_ok; then
    ok "有對外網路"
else
    warn "目前沒有對外網路（安裝套件需要）"
    if nmcli -t -f NAME connection show --active 2>/dev/null | grep -Fxq "$AP_SSID"; then
        warn "偵測到熱點 $AP_SSID 正在運作（熱點本身無對外網路），先切回一般 WiFi…"
        nmcli connection down "$AP_SSID" >/dev/null 2>&1 || true
        sleep 10
    fi
    if net_ok; then
        ok "已恢復對外網路"
    else
        die "仍無網路。請先連上可上網的 WiFi 再重跑；熱點會在最後一步自動開啟。"
    fi
fi

# ============================================================================
step "1. 系統套件 (apt)"
# ============================================================================
if [ "$SKIP_APT" = 0 ]; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -y || die "apt-get update 失敗"
    apt-get install -y --no-install-recommends \
        python3-pip python3-dev python3-pil \
        libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 \
        libsrtp2-1 libopus0 \
        fonts-arphic-uming \
        openssl curl git ca-certificates iw \
        network-manager \
        || die "系統套件安裝失敗"
    ok "基本系統套件完成（含中文字型、OpenCV/aiortc 相依、NetworkManager）"

    if apt-get install -y --no-install-recommends python3-libnvinfer python3-libnvinfer-dev; then
        ok "TensorRT Python (python3-libnvinfer) 已安裝"
    else
        warn "python3-libnvinfer 安裝失敗（需 JetPack 的 NVIDIA apt 源）；TensorRT engine 將無法匯出，會自動用 .pt"
    fi
else
    warn "略過（--skip-apt）"
fi

# ============================================================================
step "2. Python 套件 (pip --user)"
# ============================================================================
if [ "$SKIP_PIP" = 0 ]; then
    py -m pip install --user --upgrade pip >/dev/null 2>&1 || warn "pip 升級略過"

    echo "  → torch / torchvision（Jetson JP6/CU126 索引）"
    py -m pip install --user --index-url "$JETSON_PIP_INDEX" \
        "torch==2.11.0" "torchvision==0.26.0" \
        || die "torch/torchvision 安裝失敗（檢查網路或 JETSON_PIP_INDEX）"
    ok "torch 2.11.0 / torchvision 0.26.0"

    echo "  → 應用套件（PyPI）"
    py -m pip install --user \
        "numpy==2.2.6" \
        "ultralytics==8.4.177" \
        "aiortc==1.15.0" \
        "av==17.1.0" \
        "opencv-python==5.0.0.93" \
        "fastapi==0.109.0" \
        "uvicorn==0.27.0" \
        "python-multipart==0.0.32" \
        "requests==2.34.2" \
        "paramiko==2.9.3" \
        "onnx==1.23.2" \
        "onnxslim==0.1.98" \
        || die "應用套件安裝失敗"
    ok "ultralytics / aiortc / opencv / fastapi …"

    echo "  → torch CUDA 執行期補丁（libcudss）"
    py -m pip install --user --no-deps "nvidia-cudss-cu12==0.8.0.10" \
        || warn "nvidia-cudss-cu12 安裝失敗（torch GPU 可能受影響）"
else
    warn "略過（--skip-pip）"
fi

# ============================================================================
step "3. libcudss 動態連結設定"
# ============================================================================
if [ -d "$CUDSS_DIR" ]; then
    echo "$CUDSS_DIR" > /etc/ld.so.conf.d/cudss.conf
    ldconfig
    ok "已加入 ld.so 路徑：$CUDSS_DIR"
else
    warn "找不到 $CUDSS_DIR（若 torch 可正常用 GPU 可忽略）"
fi

# ============================================================================
step "4. Ollama（本機 LLM 診斷）"
# ============================================================================
if [ "$SKIP_OLLAMA" = 0 ]; then
    if ! command -v ollama >/dev/null 2>&1; then
        echo "  → 安裝 Ollama…"
        curl -fsSL https://ollama.com/install.sh | sh || die "Ollama 安裝失敗"
    else
        ok "Ollama 已存在（$(ollama --version 2>/dev/null | head -1)）"
    fi
    id ollama >/dev/null 2>&1 || useradd -r -s /bin/false -m -d /usr/share/ollama ollama
    [ -f "$SYSTEMD_SRC/ollama.service" ] && cp "$SYSTEMD_SRC/ollama.service" /etc/systemd/system/ollama.service
    systemctl daemon-reload
    systemctl enable ollama >/dev/null 2>&1
    systemctl restart ollama
    sleep 4
    echo "  → 下載模型 $OLLAMA_MODEL（首次約 800MB~1GB）…"
    ollama pull "$OLLAMA_MODEL" || warn "模型下載失敗，可稍後手動：ollama pull $OLLAMA_MODEL"
    ok "Ollama 就緒"
else
    warn "略過（--skip-ollama）"
fi

# ============================================================================
step "5. systemd 服務（開機自啟）"
# ============================================================================
[ -d "$SYSTEMD_SRC" ] || die "找不到 $SYSTEMD_SRC"
cp "$SYSTEMD_SRC"/*.service /etc/systemd/system/
systemctl daemon-reload
ok "已安裝：$(ls "$SYSTEMD_SRC" | tr '\n' ' ')"
# 逐項啟用（WebUI 待憑證/模型就緒後才啟動，見步驟 11）
for u in jetson-clocks.service ollama.service sixseven-ap.service sixseven-webrtc.service; do
    systemctl enable "$u" >/dev/null 2>&1 && ok "enable $u"
done
# oneshot 單位用 restart 才會重新套用（start 對已 active 的單位是 no-op）
systemctl restart jetson-clocks.service 2>/dev/null && ok "jetson-clocks 已套用（GPU 定頻最高）"

# ============================================================================
step "6. 埠號 sysctl（允許非 root 綁 443/80）"
# ============================================================================
cat > /etc/sysctl.d/99-unprivileged-ports.conf <<'EOF'
# 允許非 root 綁 443 (HTTPS) 與 80 (HTTP->HTTPS 轉址)
# 切勿改回 1024：systemd 服務以非 root 的 sixseven 執行，會綁不到而啟動失敗
net.ipv4.ip_unprivileged_port_start=80
EOF
sysctl --system >/dev/null 2>&1
ok "ip_unprivileged_port_start=80（$(sysctl -n net.ipv4.ip_unprivileged_port_start)）"

# ============================================================================
step "7. sudoers 與 tmpfiles"
# ============================================================================
mkdir -p /etc/sudoers.d /etc/tmpfiles.d
cat > /etc/sudoers.d/sixseven-webrtc <<EOF
# 允許 $TARGET_USER 免密碼重啟/查詢 WebUI 服務（tools/start_webrtc.sh 與 deploy_watcher 使用）
$TARGET_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart sixseven-webrtc, /usr/bin/systemctl start sixseven-webrtc, /usr/bin/systemctl stop sixseven-webrtc, /usr/bin/systemctl status sixseven-webrtc
EOF
chmod 0440 /etc/sudoers.d/sixseven-webrtc
visudo -cf /etc/sudoers.d/sixseven-webrtc >/dev/null 2>&1 && ok "sudoers 已設定" || warn "sudoers 語法檢查失敗，請確認"

cat > /etc/tmpfiles.d/opencode-tmpfiles.conf <<EOF
# 開機時自動建立 /tmp/opencode 並還原 start_webrtc.sh（/tmp 會被清空）
d /tmp/opencode 0775 $TARGET_USER $TARGET_USER -
C /tmp/opencode/start_webrtc.sh 0755 $TARGET_USER $TARGET_USER - $PROJECT_DIR/tools/start_webrtc.sh
EOF
systemd-tmpfiles --create /etc/tmpfiles.d/opencode-tmpfiles.conf >/dev/null 2>&1
ok "tmpfiles 已設定（/tmp/opencode 開機自動建立）"

# ============================================================================
step "8. cron 排程（自動部署 + 訓練監控）"
# ============================================================================
CRON_TMP="$(mktemp)"
crontab -u "$TARGET_USER" -l 2>/dev/null | grep -vE 'deploy_watcher\.py|train_monitor\.py' > "$CRON_TMP" || true
cat >> "$CRON_TMP" <<EOF

# MODEL auto-deploy watcher（每 5 分）— 偵測筆電訓練完成，拉回 best.pt 並重啟服務
*/5 * * * * /usr/bin/python3 $PROJECT_DIR/tools/deploy_watcher.py

# Training progress monitor（每 15 分）— 寫進度到 /tmp/opencode/train_monitor.log
*/15 * * * * /usr/bin/python3 $PROJECT_DIR/tools/train_monitor.py >/dev/null 2>&1
EOF
crontab -u "$TARGET_USER" "$CRON_TMP" && ok "cron 已安裝"
rm -f "$CRON_TMP"

# ============================================================================
step "9. HTTPS 憑證（含熱點固定 IP $AP_IP）"
# ============================================================================
( cd "$WEBUI_DIR" && AP_IP="$AP_IP" run_as bash ./gen_cert.sh ) || warn "憑證產生失敗"
[ -f "$WEBUI_DIR/certs/cert.pem" ] && ok "憑證就緒：$WEBUI_DIR/certs/cert.pem"

# 模型確認（.pt 由 git 帶進來）
if [ -f "$WEBUI_DIR/models/yolo11s.pt" ]; then
    ok "診斷模型 yolo11s.pt 存在"
else
    warn "找不到 $WEBUI_DIR/models/yolo11s.pt — 請 git pull 或從筆電複製"
fi

# ============================================================================
step "10. TensorRT engine（選用）"
# ============================================================================
if [ "$WITH_ENGINE" = 1 ]; then
    if [ -f "$WEBUI_DIR/models/yolo11s.pt" ]; then
        echo "  → 匯出 engine（imgsz=640, FP16；約 5~10 分鐘）…"
        ( cd "$WEBUI_DIR" && run_as python3 convert_model.py models/yolo11s.pt ) \
            && ok "engine 完成：models/yolo11s.engine" \
            || warn "engine 匯出失敗，系統仍可用 .pt（較慢）"
    else
        warn "缺少 yolo11s.pt，略過"
    fi
else
    warn "略過（未加 --with-engine；日後可補：cd webUI_workspace && python3 convert_model.py models/yolo11s.pt）"
fi

# ============================================================================
step "11. 啟動 WebUI（HTTPS :443 + HTTP :80 轉址）"
# ============================================================================
systemctl restart sixseven-webrtc
sleep 12
if systemctl is-active --quiet sixseven-webrtc; then
    ok "sixseven-webrtc 運行中"
    grep -E 'Models loaded|Uvicorn running|轉址' /tmp/opencode/https_webrtc27.log 2>/dev/null | tail -3 || true
else
    warn "sixseven-webrtc 未啟動，請看：journalctl -u sixseven-webrtc -n 50"
fi

# ============================================================================
step "12. mDNS 主機名（sixseven-project.local）"
# ============================================================================
# 讓 .local 解析到 Wi-Fi IP，而不是 docker0（172.17.0.1）等虛擬橋接位址；
# 否則手機用 http://sixseven-project.local 會連到連不到的位址而卡住/逾時。
if [ -f /etc/avahi/avahi-daemon.conf ]; then
    if ! grep -q '^deny-interfaces=' /etc/avahi/avahi-daemon.conf; then
        sed -i 's|^use-ipv6=yes|use-ipv6=yes\ndeny-interfaces=docker0,l4tbr0,usb0,usb1|' /etc/avahi/avahi-daemon.conf
    fi
    # 關 IPv6：本機只有 link-local fe80::，avahi 發 AAAA 會讓手機先試 IPv6 逾時才退回 IPv4。
    if grep -q '^use-ipv6=yes' /etc/avahi/avahi-daemon.conf; then
        sed -i 's|^use-ipv6=yes|use-ipv6=no|' /etc/avahi/avahi-daemon.conf
    fi
    systemctl restart avahi-daemon >/dev/null 2>&1
    ok "avahi：已排除虛擬介面 + 關 IPv6，.local 指向 Wi-Fi IPv4"
else
    warn "找不到 /etc/avahi/avahi-daemon.conf（avahi 未安裝？.local 可能不可用）"
fi

# ============================================================================
step "13. 開啟 WiFi 熱點（最後一步）"
# ============================================================================
# 讓熱點用戶端能用主機名連服務（短名 sixseven-project 與 .local 都指向 AP IP）
HOST_SHORT="${HOST_SHORT:-$(hostname | sed 's/\..*//')}"
mkdir -p /etc/NetworkManager/dnsmasq-shared.d
cat > /etc/NetworkManager/dnsmasq-shared.d/sixseven-host.conf <<EOF
# 由 tools/setup_env.sh 產生：熱點用戶端主機名 → AP IP
address=/$HOST_SHORT/$AP_IP
address=/$HOST_SHORT.local/$AP_IP
EOF
ok "AP DNS 主機名設定：$HOST_SHORT / $HOST_SHORT.local → $AP_IP"

if nmcli -t -f NAME connection show 2>/dev/null | grep -Fxq "$AP_SSID"; then
    ok "熱點設定檔 $AP_SSID 已存在"
    nmcli connection modify "$AP_SSID" \
        connection.autoconnect yes connection.autoconnect-priority 100 \
        wifi.mode ap ipv4.method shared ipv4.addresses "$AP_IP/24" >/dev/null 2>&1
else
    echo "  → 建立熱點設定檔 $AP_SSID…"
    nmcli connection add type wifi ifname "$AP_DEV" con-name "$AP_SSID" ssid "$AP_SSID" \
        wifi.mode ap wifi.band bg wifi.channel 1 \
        wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$AP_PASS" \
        ipv4.method shared ipv4.addresses "$AP_IP/24" \
        connection.autoconnect yes connection.autoconnect-priority 100 \
        >/dev/null 2>&1 || die "建立熱點設定檔失敗（WiFi 介面 $AP_DEV 不存在？）"
    ok "熱點設定檔已建立"
fi
systemctl restart sixseven-ap.service >/dev/null 2>&1
sleep 3
if nmcli -t -f NAME connection show --active 2>/dev/null | grep -Fxq "$AP_SSID"; then
    ok "熱點 $AP_SSID 已開啟（$AP_IP）"
else
    warn "熱點未開啟，請看：journalctl -u sixseven-ap -n 30"
fi

# ============================================================================
echo
echo "${BOLD}${GRN}===== 完成 =====${RST}"
echo "  手機：連 WiFi「${BOLD}$AP_SSID${RST}」(密碼 $AP_PASS) → 瀏覽器輸入 ${BOLD}$AP_IP${RST} / ${BOLD}$HOST_SHORT${RST} / ${BOLD}$HOST_SHORT.local${RST}"
echo "        （會自動從 http 跳到 https；首次需點「進階 → 繼續前往」信任自簽憑證）"
echo "  服務：systemctl status sixseven-webrtc　log：/tmp/opencode/https_webrtc27.log"
echo "  狀態：curl -k https://$AP_IP/status"
echo
