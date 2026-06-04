import argparse
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import quote

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


CITY_CODES = {
    "全国": "100010000",
    "北京": "101010100",
    "上海": "101020100",
    "广州": "101280100",
    "深圳": "101280600",
    "杭州": "101210100",
    "成都": "101270100",
    "武汉": "101200100",
    "南京": "101190100",
    "苏州": "101190400",
}


def clean_text(text):
    return re.sub(r"\s+", " ", text or "").strip()


def first_text(card, selectors):
    for selector in selectors:
        try:
            item = card.query_selector(selector)
            if item:
                text = clean_text(item.inner_text())
                if text:
                    return text
        except Exception:
            continue
    return ""


def first_attr(card, selectors, attr):
    for selector in selectors:
        try:
            item = card.query_selector(selector)
            if item:
                value = item.get_attribute(attr)
                if value:
                    return value
        except Exception:
            continue
    return ""


def normalize_url(url):
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://www.zhipin.com" + url
    return url


def split_info(text):
    parts = [part.strip() for part in re.split(r"[|·]", text or "") if part.strip()]
    return parts


def parse_card(card):
    full_text = clean_text(card.inner_text())
    info_parts = split_info(full_text)

    title = first_text(card, [".job-name", ".job-title", "[class*=job-name]"])
    salary = first_text(card, [".salary", ".red", "[class*=salary]"])
    company = first_text(card, [".company-name", "[class*=company-name]", ".boss-name"])
    location = first_text(card, [".job-area", "[class*=job-area]"])
    experience = first_text(card, [".job-info .tag-list li:nth-child(1)", ".job-info li:nth-child(1)"])
    education = first_text(card, [".job-info .tag-list li:nth-child(2)", ".job-info li:nth-child(2)"])
    link = normalize_url(first_attr(card, ["a[href*='/job_detail/']"], "href"))

    if not title and info_parts:
        title = info_parts[0]
    if not salary:
        salary_match = re.search(r"(\d+\s*-\s*\d+K|\d+K以上|\d+K以下|\d+\s*-\s*\d+元/天)", full_text)
        salary = salary_match.group(1) if salary_match else ""

    return {
        "岗位名称": title,
        "薪资": salary,
        "公司": company,
        "地点": location,
        "经验": experience,
        "学历": education,
        "链接": link,
    }


def collect_jobs(keyword, city_code, limit, headless, wait_seconds):
    url = f"https://www.zhipin.com/web/geek/job?query={quote(keyword)}&city={city_code}"
    jobs = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        page = browser.new_page(
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
        )
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        if not headless:
            print("页面已打开。如果出现登录、滑块或验证码，请先在浏览器里完成。")
            print(f"脚本将在 {wait_seconds} 秒后开始读取页面岗位信息。")
            time.sleep(wait_seconds)

        try:
            page.wait_for_selector(
                ".job-card-wrapper, .job-list-box li, a[href*='/job_detail/']",
                timeout=30000,
            )
        except PlaywrightTimeoutError:
            browser.close()
            raise RuntimeError("没有读取到岗位列表，可能需要登录、验证，或页面结构已经变化。")

        for _ in range(5):
            cards = page.query_selector_all(".job-card-wrapper")
            if not cards:
                cards = page.query_selector_all(".job-list-box li")
            if len(cards) >= limit:
                break
            page.mouse.wheel(0, 900)
            time.sleep(1)

        cards = page.query_selector_all(".job-card-wrapper")
        if not cards:
            cards = page.query_selector_all(".job-list-box li")

        seen = set()
        for card in cards:
            job = parse_card(card)
            key = (job["岗位名称"], job["公司"], job["链接"])
            if not job["岗位名称"] or key in seen:
                continue
            seen.add(key)
            jobs.append(job)
            if len(jobs) >= limit:
                break

        browser.close()

    return jobs


def save_results(jobs, output_path):
    output = Path(output_path)
    if output.suffix.lower() == ".json":
        output.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")
        return

    with output.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["岗位名称", "薪资", "公司", "地点", "经验", "学历", "链接"],
        )
        writer.writeheader()
        writer.writerows(jobs)


def main():
    parser = argparse.ArgumentParser(description="抓取 BOSS 直聘关键词下的前 N 个岗位信息")
    parser.add_argument("keyword", help="搜索关键词，例如：数据分析")
    parser.add_argument("--city", default="全国", help="城市名，默认：全国")
    parser.add_argument("--city-code", default="", help="BOSS 直聘城市代码；填写后优先使用")
    parser.add_argument("--limit", type=int, default=10, help="抓取数量，默认：10")
    parser.add_argument("--output", default="boss_jobs.csv", help="输出文件，支持 .csv 或 .json")
    parser.add_argument("--headless", action="store_true", help="无界面运行；遇到验证时不建议使用")
    parser.add_argument("--wait", type=int, default=20, help="打开页面后等待多少秒再读取，默认：20")
    args = parser.parse_args()

    city_code = args.city_code or CITY_CODES.get(args.city)
    if not city_code:
        city_names = "、".join(CITY_CODES)
        raise SystemExit(f"暂不认识城市“{args.city}”，可用城市：{city_names}；或使用 --city-code 填代码。")

    jobs = collect_jobs(args.keyword, city_code, args.limit, args.headless, args.wait)
    save_results(jobs, args.output)

    print(f"已抓取 {len(jobs)} 条岗位信息，保存到：{Path(args.output).resolve()}")
    for index, job in enumerate(jobs, 1):
        print(f"{index}. {job['岗位名称']} | {job['薪资']} | {job['公司']} | {job['地点']}")


if __name__ == "__main__":
    main()
