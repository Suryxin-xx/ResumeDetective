"""ResumeDetective v4 browser smoke test.

Run against an isolated development server. The script never opens the user's
production data directory.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright


BASE_URL = "http://127.0.0.1:18765"
OUTPUT = Path(__file__).resolve().parents[2] / "local-artifacts" / "v4-qa"


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 980})
        console_errors: list[str] = []
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)

        page.goto(BASE_URL, wait_until="networkidle")
        page.get_by_role("heading", name="秋招工作台").wait_for()
        page.get_by_role("button", name="＋ 新建投递").click()
        page.get_by_label("公司名称").fill("浏览器验证公司")
        page.get_by_label("岗位名称").fill("Go 后端开发")
        page.get_by_label("城市").fill("上海")
        page.get_by_label("岗位类型").fill("研发")
        page.get_by_label("自定义标签").fill("Go, 校招")
        page.get_by_label("JD 原文").fill("负责本地优先的求职工作台开发。")
        page.get_by_role("button", name="保存为已投递").click()
        page.get_by_text("浏览器验证公司").wait_for()

        page.get_by_role("button", name="投递管理").click()
        page.get_by_placeholder("搜索公司、岗位或标签").fill("Go")
        page.get_by_text("Go 后端开发").wait_for()
        page.screenshot(path=str(OUTPUT / "applications.png"), full_page=True)

        page.get_by_role("button", name="简历汇总").click()
        page.get_by_role("heading", name="简历汇总").wait_for()
        page.get_by_role("button", name="配套工具").click()
        page.get_by_role("heading", name="ImagePDFConverter").wait_for()
        page.screenshot(path=str(OUTPUT / "tools.png"), full_page=True)

        if console_errors:
            raise AssertionError(f"browser console errors: {console_errors}")
        browser.close()


if __name__ == "__main__":
    main()
