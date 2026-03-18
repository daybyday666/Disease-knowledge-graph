import pandas as pd
from crawler.dxy_crawler import get_disease_list, get_disease_info

triples = []
diseases = get_disease_list()
for disease in diseases[:200]:  
    info = get_disease_info(disease["url"])
    for symptom in info["symptoms"]:
        triples.append([info["name"], "有症状", symptom])
    for treatment in info["treatments"]:
        triples.append([info["name"], "治疗方法", treatment])
    triples.append([info["name"], "所属科室", info["department"]])

df = pd.DataFrame(triples, columns=["疾病", "关系", "实体"])
df = df.drop_duplicates()
df.to_csv("disease_triples.csv", index=False, encoding="utf-8-sig")