#!/usr/bin/env python3
"""訓練自動部署 watcher:
每 5 分鐘由 cron 執行。偵測筆電上的訓練程式(train_bal*.py)結束後,
把最新的 best.pt 從筆電抓回 Jetson,與目前 models/yolo11s.pt 比較,
若不同(size 不同)就覆蓋並重啟服務。lock 檔防止重複部署。
"""
import os, time, subprocess
import paramiko

LAPTOP = "192.168.0.111"
LUSER = "alice"
LPASS = "1"
REMOTE_WEIGHTS = "/home/alice/runs/train-bal-7cls/weights/best.pt"
DEPLOY_DST = "/home/sixseven/sixseven-project/webUI_workspace/models/yolo11s.pt"
DEPLOY_TMP = "/tmp/opencode/new_best.pt"
LOCK = "/tmp/opencode/deployed.lock"
WLOG = "/tmp/opencode/deploy_watcher.log"


def log(msg):
    with open(WLOG, "a") as f:
        f.write(f"{time.strftime('%F %T')} {msg}\n")


def ssh_connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(LAPTOP, username=LUSER, password=LPASS, timeout=15)
    return c


def main():
    # 已部署過就不要再動(lock 存在即結束)
    if os.path.exists(LOCK):
        return

    try:
        c = ssh_connect()
    except Exception as e:
        log(f"SSH 失敗: {e}")
        return

    try:
        # 1. 訓練進程還在跑嗎?
        _, out, _ = c.exec_command("ps aux | grep -E 'train_bal(_fast)?\\.py' | grep -v grep | wc -l", timeout=30)
        n = out.read().decode().strip()
        if n != "0":
            log(f"訓練中(proc={n}) skip")
            return

        # 2. 訓練結束:取得筆電上 best.pt 資訊
        sftp = c.open_sftp()
        try:
            st = sftp.stat(REMOTE_WEIGHTS)
            rmt = (st.st_size, st.st_mtime)
        except Exception as e:
            sftp.close()
            log(f"best.pt 不存在: {e}")
            return

        # 3. 本機現有模型資訊
        local = None
        if os.path.exists(DEPLOY_DST):
            ls = os.stat(DEPLOY_DST)
            local = (ls.st_size, ls.st_mtime)

        # 4. size 相同 = 已部署過,直接 lock
        if local and local[0] == rmt[0]:
            sftp.close()
            open(LOCK, "w").write("")
            log("best.pt 已是最新版,直接 lock(不重啟)")
            return

        # 5. 下載新的 best.pt 並覆蓋本機模型
        try:
            sftp.get(REMOTE_WEIGHTS, DEPLOY_TMP)
        finally:
            sftp.close()
        if not os.path.exists(DEPLOY_TMP) or os.path.getsize(DEPLOY_TMP) == 0:
            log("下載失敗(0 bytes)")
            return

        os.replace(DEPLOY_TMP, DEPLOY_DST)
        log(f"已更新 {DEPLOY_DST} size={os.path.getsize(DEPLOY_DST)}")
    except Exception as e:
        log(f"watcher 錯誤: {e}")
        return
    finally:
        try:
            c.close()
        except Exception:
            pass

    # 6. 更新模型後重啟服務
    try:
        r = subprocess.run(["bash", "/tmp/opencode/start_webrtc.sh"], capture_output=True, timeout=60)
        log(f"重啟服務: {r.stdout.decode().strip()}")
        open(LOCK, "w").write("")
    except Exception as e:
        log(f"重啟失敗: {e}")


if __name__ == "__main__":
    main()