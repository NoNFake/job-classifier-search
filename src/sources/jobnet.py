import requests
import json
from tabulate import tabulate

urls = [
    "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=200&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000",
    "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=200&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000&occupationGroups=110050&occupations=8b6456a3-ae9a-45a0-a65b-fed797521753",
    "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=200&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000&occupationGroups=110020&occupations=5faefc93-a834-4749-9297-8a13012022fa",
    
]

# url = "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=10&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000&occupationGroups=110050&occupations=8b6456a3-ae9a-45a0-a65b-fed797521753"
# https://jobnet.dk/find-job?postalCode=2200&occupationAreas=110000&occupationGroups=110050&occupations=8b6456a3-ae9a-45a0-a65b-fed797521753
session = requests.Session()
session.headers.clear()

headers = {
    "X-Csrf": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",  # Добавим на всякий случай легкий спуфинг
    "Accept": "*/*",
}

job_ads_list = []
seen_ids = set()

for url in urls:
# for url in urls
    with session.get(url, headers=headers) as resp:
        data_json =resp.json()
        print(url)
        d = data_json.get("jobAds", [])
        print(len(d))
        # job_ads_list.update(d)
        for job in d:
             job_id = job.get("jobAdId")

             if job_id not in seen_ids:
                  seen_ids.add(job_id)
                  job_ads_list.append(job)
    # print(str(data_json)[:500])
    # print(list(data_json.keys()))

# print(len(job_ads_list))

print(f" found: {len(job_ads_list)}".center(60))
table_data = []
# for index, job in enumerate(job_ads_list, 1):
#     title = job.get("title", "null").upper()
#     company = job.get("company", "null")
#     city = job.get("city", "null")
#     post_code = job.get("post_code", "null")
#     link = job.get("link", "null")

for index, job in enumerate(job_ads_list, 1):
        table_data.append([
                index,
                job.get("hiringOrgName", "-"),
                job.get("title", "—")[:40], 
                f"{job.get('postalCode', '')} {job.get('postalDistrictName', '')}"

        ])
headres_table = ["#", "company", "position", "location"]
print(tabulate(table_data, headers=headres_table, tablefmt="rounded_grid" ))
