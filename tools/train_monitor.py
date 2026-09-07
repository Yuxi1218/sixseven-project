#!/usr/bin/env python3
"""定時監控筆電訓練進度,摘要寫入 /tmp/opencode/train_monitor.log。
訓練結束或異常時標記狀態。手動執行或由 cron 每 15 分鐘跑。"""
import time, datetime
import paramiko

LAPTOP = "192.168.0.111"
LUSER = "alice"
LPASS = "1"
LOG = "/tmp/opencode/train_monitor.log"
RLOG = "~/train_bal_fast.log"
CSV = "~/runs/train-bal-7cls/results.csv"


def log(msg):
    with open(LOG, "a") as f:
        f.write(f"{datetime.datetime.now():%F %T} {msg}\n")
    print(msg)


def main():
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(LAPTOP, username=LUSER, password=LPASS, timeout=15)
    except Exception as e:
        log(f"SSH 失敗 {e}")
        return

    try:
        # 訓練進程
        _, out, _ = c.exec_command("ps aux | grep -E 'train_bal(_fast)?\\.py' | grep -v grep | wc -l", timeout=30)
        running = out.read().decode().strip()

        # 進度(取最後一行的 epoch / 完成%
        _, out, _ = c.exec_command(f"tail -c 200 {RLOG} | tr -d '\\r'", timeout=30)
        tail = out.read().decode(errors="replace").strip()

        # results.csv 最新三行(整體指標)
        _, out, _ = c.exec_command(f"awk -F, 'NR>1{{print $1, $6, $7, $8}}' {CSV} | tail -3", timeout=30)
        csv = out.read().decode(errors="replace").strip()

        # 權重時間
        _, out, _ = c.exec_command("ls -la --time-style=+%m-%d_%H:%M ~/runs/train-bal-7cls/weights/best.pt", timeout=30)
        wt = out.read().decode(errors="replace").strip()

        c.close()

        state = "RUNNING" if running != "0" else "DONE"
        log(f"[{state}] proc={running}")
        log(f"  tail: {tail[-90:]}")
        log(f"  results.csv(last): {csv or 'N/A(第一輪未完成)'}")
        log(f"  best.pt: {wt}")
    except Exception as e:
        try:
            c.close()
        except Exception:
            pass
        log(f"查詢錯誤 {e}")


if __name__ == "__main__":
    main()