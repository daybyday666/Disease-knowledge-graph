"""丁香园页面辅助抓取脚本

核心用途（数据收集）：
- filter_section_tags: 以已有的 disease_kg.csv 疾病集合过滤科室页标签列表，得到 section_tags_filtered.csv 作为抓取清单；
- get_dxy_sections: 按疾病 tag_id 抓取详情页，解析“简介/病因/症状/诊断/治疗”正文；
- main: 逐个疾病调用 get_dxy_sections，分别写出 5 个 CSV 文件。

说明：
- 该脚本偏向“稳健抓取”，包含重试/限速/反爬字样检测；
- 页面结构如变化，选择器需相应调整。
"""

def filter_section_tags():
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    section_tags_path = os.path.join(base_dir, "section_tags.csv")
    kg_path = os.path.join(base_dir, "..", "disease_kg.csv")
    # 读取 disease_kg.csv 疾病名集合，作为白名单
    kg_names = set()
    with open(kg_path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0]:
                kg_names.add(row[0].strip())
    filtered_rows = []
    with open(section_tags_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames
        for row in reader:
            name = row.get("tag_name")
            if name and name.strip() in kg_names:
                filtered_rows.append(row)
    # 保存为新文件
    filtered_path = os.path.join(base_dir, "section_tags_filtered.csv")
    with open(filtered_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(filtered_rows)
    print(f"已生成只包含 disease_kg.csv 疾病的 section_tags_filtered.csv，共 {len(filtered_rows)} 条。")


import csv
import requests
from bs4 import BeautifulSoup


def get_dxy_sections(tag_id):
    """
    返回dict: {"简介":..., "病因":..., "症状":..., "诊断":..., "治疗":...,}
    """
    import time, random
    url = f"https://dxy.com/disease/{tag_id}/detail"
    result = {"简介": "", "病因": "", "症状": "", "诊断": "", "治疗": ""}
    max_retries = 5
    for attempt in range(1, max_retries + 1):
        try:
            print(f"[INFO] 请求tag_id={tag_id}, 尝试第{attempt}次: {url}")
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": "https://dxy.com/",
            }
            resp = requests.get(url, headers=headers, timeout=15)
            print(f"[DEBUG] 状态码: {resp.status_code}")
            if resp.status_code != 200:
                print(f"[WARN] 状态码异常: {resp.status_code}, 等待重试...")
                time.sleep(random.uniform(10, 20))
                continue
            if "访问受限" in resp.text or "验证码" in resp.text or "人机验证" in resp.text:
                print(f"[WARN] 可能被封/反爬，返回内容包含访问受限/验证码，等待重试...")
                print(f"[DEBUG] 返回内容片段: {resp.text[:200]}")
                time.sleep(random.uniform(20, 40))
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            # 选择疾病详情卡片（类名包含 disease-detail-card），不同页面结构可能差异
            cards = soup.find_all(lambda tag: tag.name == "div" and tag.get("class") and "disease-detail-card" in " ".join(tag.get("class")))
            for card in cards:
                title_tag = card.find("p", class_=lambda x: x and "disease-detail-card-title" in x) or card.find("h2")
                main_title = title_tag.get_text(strip=True) if title_tag else ""
                # 内容区域有时在 div.html-parse 或 div.tag-html 内，缺失时退回 card 全文
                content_div = card.find(lambda t: t.name == "div" and t.get("class") and ("html-parse" in " ".join(t.get("class")) or "tag-html" in " ".join(t.get("class"))))
                content_div = content_div if content_div else card
                txt = content_div.get_text(separator="\n", strip=True)
                if not txt:
                    continue
                if "简介" in main_title or (not main_title and not result["简介"]):
                    result["简介"] = txt
                elif "病因" in main_title or "原因" in main_title:
                    result["病因"] = txt
                elif "症状" in main_title:
                    result["症状"] = txt
                elif "诊断" in main_title:
                    result["诊断"] = txt
                elif "治疗" in main_title:
                    result["治疗"] = txt
            # 兜底简介
            if not result["简介"]:
                p = soup.find("p")
                if p:
                    result["简介"] = p.get_text(strip=True)
            print(f"[INFO] tag_id={tag_id} 抓取成功。")
            return result
        except Exception as e:
            print(f"[ERROR] tag_id={tag_id} 抓取异常: {e}")
            time.sleep(random.uniform(10, 20))
    print(f"[FAIL] tag_id={tag_id} 多次重试失败，跳过。")
    return result

def main():
    diseases = []
    import os
    base_dir = os.path.dirname(os.path.abspath(__file__))
    section_tags_path = os.path.join(base_dir, "section_tags_filtered.csv")
    with open(section_tags_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("tag_name")
            tag_id = row.get("tag_id")
            if name and tag_id:
                diseases.append((name, tag_id))

    # 先收集所有内容
    intro_rows = []
    cause_rows = []
    symptom_rows = []
    diagnosis_rows = []
    treatment_rows = []
    import time, random
    for idx, (name, tag_id) in enumerate(diseases, 1):
        print(f"\n[PROGRESS] 正在处理第{idx}/{len(diseases)}个: {name} (tag_id={tag_id})")
        sections = get_dxy_sections(tag_id)
        intro_rows.append([name, sections.get("简介", "")])
        cause_rows.append([name, sections.get("病因", "")])
        symptom_rows.append([name, sections.get("症状", "")])
        diagnosis_rows.append([name, sections.get("诊断", "")])
        treatment_rows.append([name, sections.get("治疗", "")])
        # 随机等待，减轻被封风险
        sleep_time = random.uniform(5, 10)
        print(f"[SLEEP] 等待{sleep_time:.1f}秒防止被封...")
        time.sleep(sleep_time)

    # 分别写入不同文件
    with open("disease_dxy_intro.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["疾病名称", "简介"])
        writer.writerows(intro_rows)
    with open("disease_dxy_cause.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["疾病名称", "病因"])
        writer.writerows(cause_rows)
    with open("disease_dxy_symptom.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["疾病名称", "症状"])
        writer.writerows(symptom_rows)
    with open("disease_dxy_diagnosis.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["疾病名称", "诊断"])
        writer.writerows(diagnosis_rows)
    with open("disease_dxy_treatment.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["疾病名称", "治疗"])
        writer.writerows(treatment_rows)

if __name__ == "__main__":
    main()