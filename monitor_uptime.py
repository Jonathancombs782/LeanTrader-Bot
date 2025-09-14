import os
import time

import psutil


def check_bot():
    for proc in psutil.process_iter(["pid", "name"]):
        if "python" in proc.info["name"] and "brain_loop.py" in " ".join(proc.cmdline()):
            return True
    return False


def main():
    while True:
        if not check_bot():
            os.system("systemctl restart leantrader")  # Restart service
        time.sleep(60)


if __name__ == "__main__":
    main()
