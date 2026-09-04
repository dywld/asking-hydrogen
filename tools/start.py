"""더블클릭용 시작 도우미 — 시작.bat / 시작.command 가 부른다.

하는 일: 필요한 것 설치 → 키 없으면 물어봄 → 서버 켬 → 브라우저 자동으로 엶.
두 번째부터는 설치·키 단계를 건너뛰고 바로 켠다.
"""
import os
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = int(os.environ.get("BOT_PORT") or 8000)
URL = f"http://localhost:{PORT}"
KEY = ROOT / "key.txt"


def say(msg):
    print(f"\n▶ {msg}", flush=True)


def is_up():
    try:
        urllib.request.urlopen(URL + "/api/status", timeout=2)
        return True
    except Exception:
        return False


def ensure_packages():
    try:
        import numpy  # noqa: F401
        return
    except ImportError:
        pass
    say("필요한 것을 설치합니다 (처음 한 번, 1분 정도)")
    r = subprocess.call([sys.executable, "-m", "pip", "install", "-q", "numpy"])
    if r != 0:
        say("설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.")
        sys.exit(1)


def ensure_key():
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return
    if KEY.exists() and KEY.read_text(encoding="utf-8").strip():
        return
    say("구글 제미나이 API 키가 필요합니다 (무료, 1분).")
    print("  1) https://aistudio.google.com/apikey 열기 (지금 자동으로 엽니다)")
    print("  2) 'API 키 만들기' 누르고 나온 긴 글자를 복사")
    print("  3) 아래에 붙여넣고 Enter")
    print("  * 그냥 Enter 치면 키 없이 켜집니다 (법령 검색만 되고 답변 문장은 안 나옴)")
    if not os.environ.get("BOT_NO_BROWSER"):
        try:
            webbrowser.open("https://aistudio.google.com/apikey")
        except Exception:
            pass
    k = input("\n키 붙여넣기 > ").strip()
    if k:
        KEY.write_text(k, encoding="utf-8")
        say("key.txt 에 저장했습니다. 이 파일은 깃허브에 올라가지 않습니다.")


def open_when_ready():
    for _ in range(600):          # 최대 10분 — 첫 실행은 색인 만드느라 오래 걸릴 수 있다
        if is_up():
            say(f"열렸습니다 → {URL}   (이 창을 닫으면 서버가 꺼집니다)")
            if not os.environ.get("BOT_NO_BROWSER"):
                webbrowser.open(URL)
            return
        time.sleep(1)


def main():
    os.chdir(ROOT)
    if is_up():
        say(f"이미 켜져 있습니다 → {URL}")
        if not os.environ.get("BOT_NO_BROWSER"):
            webbrowser.open(URL)
        return
    ensure_packages()
    ensure_key()
    say("서버를 켭니다. 처음이면 1~2분 걸립니다 (법령 32,217조각 색인).")
    threading.Thread(target=open_when_ready, daemon=True).start()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        subprocess.call([sys.executable, str(ROOT / "app.py")], env=env)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
