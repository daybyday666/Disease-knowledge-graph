"""丁香园疾病页数据收集（核心爬取脚本）

功能概览（数据收集）：
- 从疾病索引页抓取链接（科室页与疾病详情页）。
- 科室页：解析“热门疾病”并产出 (疾病名, "所属科室", 科室名) 三元组。
- 疾病详情页：简单检索页面文本中的“症状/治疗”片段，产出 (疾病名, 关系, 文本) 三元组（示例级别）。
- 将三元组附加写入 CSV（默认 disease_kg.csv），供后续清洗与处理。

实现要点：
- 使用 requests 会话设置常见浏览器头，适度延时，尽量降低被反爬概率。
- 解析采用 BeautifulSoup；科室页同时支持 DOM 与页面内注入 JSON 两种来源兜底。
- main() 中通过正则将链接分为“科室页”和“疾病详情页”，分别走不同解析函数。

注意：页面结构可能随时间变化，解析规则需视实际 HTML 更新。
"""

import argparse
import csv
import logging
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import re
import json

DEFAULT_INDEX = "https://dxy.com/diseases"
LOG = logging.getLogger("dxy_crawler")


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://dxy.com/",
    })
    return s


def parse_index_for_links(html: str, base: str) -> List[str]:
    """从索引页 HTML 提取所有超链接并做绝对化、去重。

    返回值包含多种类型链接，后续会用正则筛选科室页/详情页。
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base, href)
        if full not in links:
            links.append(full)
    return links


def fetch_disease(session: requests.Session, url: str) -> List[Tuple[str, str, str]]:
    """抓取疾病详情页并做极简信息抽取（演示级）。

    逻辑：
    - 请求详情页，解析页面文本块；
    - 如果段落中包含“治疗”“症状”等关键词，则截取前 400 字作为样例尾实体文本；
    - 组装 (疾病名, 关系, 片段) 返回。

    返回的三元组可作为构建词表/词典/对齐的输入，精确抽取建议在后续处理阶段完成。
    """
    LOG.info("抓取疾病：%s", url)
    try:
        r = session.get(url, timeout=10)
    except Exception as e:
        LOG.warning("请求失败 %s: %s", url, e)
        return []
    if r.status_code != 200:
        LOG.warning("非 200 响应 %s: %s", url, r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    title_tag = soup.find("h1")
    name = title_tag.get_text(strip=True) if title_tag else url

    triples = []
    # 简单抽取页面包含“治疗”“症状”的文本片段（轻量级），供后续扩展
    for tag in soup.find_all(["p", "div", "li"]):
        try:
            txt = tag.get_text(separator=" ", strip=True)
        except Exception:
            continue
        if not txt:
            continue
        if "治疗" in txt:
            triples.append((name, "治疗方法", txt[:400]))
        if "症状" in txt:
            triples.append((name, "有症状", txt[:400]))

    return triples


def fetch_section(session: requests.Session, url: str) -> List[Tuple[str, str, str]]:
    """抓取科室页，提取热门疾病并返回 (疾病名, '所属科室', 科室名)。

    解析策略：
    1) 首选 DOM：查找包含热门疾病的块（类名 hot-disease-content），提取<a>文本；
    2) 退化到页内 JSON：正则匹配 window.$$data，解析其中 diseases/tag_list；
    3) 科室名优先取 <h1> 或 JSON 的 currentSection.name。
    """
    LOG.info("抓取科室页：%s", url)
    try:
        r = session.get(url, timeout=10)
    except Exception as e:
        LOG.warning("请求失败 %s: %s", url, e)
        return []
    if r.status_code != 200:
        LOG.warning("非 200 响应 %s: %s", url, r.status_code)
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    triples: List[Tuple[str, str, str]] = []

    # 尝试从 DOM 中读取热病块
    hot = soup.find("div", class_="hot-disease-content")
    # 尝试找到科室名（页面 <h1> 或面包屑）
    dept = None
    h1 = soup.find("h1")
    if h1:
        dept = h1.get_text(strip=True)

    if hot:
        dept = dept or "未知科室"
        for a in hot.find_all("a", href=True):
            name = a.get_text(strip=True)
            if name:
                triples.append((name, "所属科室", dept))

    # 如果 DOM 未提供 hot 列表，尝试从页面内注入的 JSON 中抽取
    if not triples:
        try:
            m = re.search(r"window\.\$\$data\s*=\s*(\{.*?\})\s*(?:;|</script>)", r.text, flags=re.S)
            if m:
                data = json.loads(m.group(1))
                diseases = data.get("diseases", [])
                tag_list = []
                for grp in diseases:
                    if grp.get("index_name") == "热门":
                        tag_list = grp.get("tag_list", [])
                        break
                if not tag_list and diseases:
                    tag_list = diseases[0].get("tag_list", [])

                dept = dept or data.get("currentSection", {}).get("name") or "未知科室"
                for tag in tag_list:
                    name = tag.get("tag_name") or tag.get("name")
                    if name:
                        triples.append((name, "所属科室", dept))
        except Exception:
            LOG.debug("从科室页内 JSON 抽取热门疾病失败 %s", url)

    return triples


def write_csv(rows: List[Tuple[str, str, str]], out_path: str = "disease_kg.csv"):
    """将抽取的三元组追加写入 CSV（若不存在则写入表头）。"""
    path = Path(out_path)
    write_header = not path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        if write_header:
            writer.writerow(["头实体", "关系", "尾实体"])
        for r in rows:
            writer.writerow(list(r))


def main():
    """命令行入口：抓取索引页，分发到科室/详情解析，并写出 kg CSV。

    关键参数：
    - --index-url：起始索引页；
    - --max：最多处理的链接数（0 表示全部）；
    - --out：输出 CSV 路径；
    - --dry-run：仅打印解析到的链接，不抓取详情；
    - --delay：每个请求后的休眠秒数，建议>1 以降低被封风险。
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-url", default=DEFAULT_INDEX, help="疾病库主页 URL")
    parser.add_argument("--max", type=int, default=0, help="最多抓取多少个链接，0 为全部")
    parser.add_argument("--out", default="disease_kg.csv", help="输出 CSV 文件")
    parser.add_argument("--dry-run", action="store_true", help="仅列出找到的链接，不抓取详情")
    parser.add_argument("--delay", type=float, default=1.0, help="每个请求后的延迟秒数")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    session = make_session()
    try:
        r = session.get(args.index_url, timeout=10)
    except Exception as e:
        LOG.error("无法获取索引页 %s: %s", args.index_url, e)
        return
    if r.status_code != 200:
        LOG.error("索引页返回 %s", r.status_code)
        return

    links = parse_index_for_links(r.text, args.index_url)
    LOG.info("在索引页发现 %d 条链接，展示前 40 条", len(links))
    for l in links[:40]:
        print(l)

    if args.dry_run:
        LOG.info("dry-run 模式，停止于此")
        return

    # 过滤并处理科室页 (/diseases/<id>) 与疾病详情页 (/disease/<id>/detail)
    section_links = [u for u in links if re.search(r"/diseases/\d+$", u)]
    disease_links = [u for u in links if "/disease/" in u]

    # 合并去重
    to_process = []
    to_process.extend(section_links)
    to_process.extend([u for u in disease_links if u not in to_process])
    if args.max and args.max > 0:
        to_process = to_process[: args.max]

    total = 0
    for url in to_process:
        rows = []
        if re.search(r"/diseases/\d+$", url):
            rows = fetch_section(session, url)
        else:
            rows = fetch_disease(session, url)
        if rows:
            write_csv(rows, args.out)
            total += len(rows)
        time.sleep(args.delay)

    LOG.info("完成，写入 %d 条到 %s", total, args.out)


if __name__ == "__main__":
    main()