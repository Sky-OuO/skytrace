"""浏览器回归：记一笔必须 POST 到表单的 action 地址，不能打到名为 action 的按钮。"""

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SENTENCE = "回归窗光侧坐靠窗不进错地址"
AUTHOR = {"email": "author@skytrace.local", "password": "author-demo-pass"}
REVIEWER = {"email": "reviewer@skytrace.local", "password": "reviewer-demo-pass"}


def _chrome() -> str | None:
    for candidate in (
        os.environ.get("CHROME_PATH"),
        "/usr/local/bin/google-chrome",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
    ):
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _png(path: Path) -> None:
    from PIL import Image

    Image.new("RGB", (16, 20), (120, 90, 70)).save(path, format="PNG")


@pytest.fixture
def live_server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=os.environ.copy(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20
    ready = False
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        try:
            with urllib.request.urlopen(base + "/", timeout=0.4) as response:
                if response.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(0.15)
    if not ready:
        output = ""
        if proc.stdout is not None:
            proc.kill()
            output = proc.stdout.read().decode("utf-8", errors="replace")[-2000:]
        pytest.fail(f"演示服务没有起来\n{output}")
    yield base
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def test_publish_posts_to_the_form_action_and_can_be_approved(live_server, tmp_path):
    pytest.importorskip("playwright.sync_api")
    chrome = _chrome()
    if chrome is None:
        pytest.skip("没有安装 Chrome 或 Chromium")
    from playwright.sync_api import sync_playwright

    image = tmp_path / "shot.png"
    _png(image)
    posts: list[str] = []

    try:
        playwright = sync_playwright().start()
        browser = playwright.chromium.launch(executable_path=chrome, args=["--no-sandbox", "--disable-gpu"])
    except Exception as exc:
        pytest.skip(f"浏览器起不来：{exc}")

    try:
        page = browser.new_page()
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)

        page.goto(live_server + "/login")
        page.fill("#email", AUTHOR["email"])
        page.fill("#password", AUTHOR["password"])
        page.get_by_role("button", name="登录").click()
        page.wait_for_load_state("networkidle")

        page.goto(live_server + "/publish?subject=window-light-portrait")
        page.set_input_files("#image", str(image))
        page.fill("#body", SENTENCE)
        page.check('input[name="portrait_auth"]')
        page.get_by_role("button", name="提交").click()
        page.locator(".toast.is-on").filter(has_text="待审").wait_for()

        publish_posts = [url for url in posts if url.rstrip("/").endswith("/publish")]
        assert publish_posts, posts
        assert all("object" not in url and "RadioNodeList" not in url for url in posts)

        page.goto(live_server + "/logout")
        page.goto(live_server + "/login")
        page.fill("#email", REVIEWER["email"])
        page.fill("#password", REVIEWER["password"])
        page.get_by_role("button", name="登录").click()
        page.wait_for_load_state("networkidle")
        page.goto(live_server + "/review")
        card = page.locator(".review-card", has_text=SENTENCE)
        card.get_by_role("button", name="通过").click()
        page.locator(".toast.is-on").filter(has_text="已通过").wait_for()

        review_posts = [url for url in posts if "/review/" in url]
        assert review_posts, posts
        assert all("object" not in url and "RadioNodeList" not in url for url in review_posts)

        page.goto(live_server + "/")
        page.get_by_text(SENTENCE).first.wait_for()
    finally:
        browser.close()
        playwright.stop()
