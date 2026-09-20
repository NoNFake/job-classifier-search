import concurrent.futures as cf

import requests
from tabulate import tabulate
from sources.cache import fetch as cached
urls = [
    "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=200&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000",
    "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=200&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000&occupationGroups=110050&occupations=8b6456a3-ae9a-45a0-a65b-fed797521753",
    "https://jobnet.dk/bff/FindJob/Search?resultsPerPage=200&pageNumber=1&orderType=BestMatch&kmRadius=50&searchString=&postalCode=2200&occupationAreas=110000&occupationGroups=110020&occupations=5faefc93-a834-4749-9297-8a13012022fa",
]

headers = {
    "X-Csrf": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "*/*",
}


def fetch(url):
    # with requests.get(url, headers=headers, timeout=30) as resp:
    #     return resp.json().get("jobAds", [])
    return cached(url, headers).get("jobAds", [])

job_ads_list = []
seen_ids = set()

with cf.ThreadPoolExecutor(8) as pool:
    for url, ads in zip(urls, pool.map(fetch, urls)):
        print(url)
        print(len(ads))
        for job in ads:
            job_id = job.get("jobAdId")
            if job_id not in seen_ids:
                seen_ids.add(job_id)
                job_ads_list.append(job)

print(f" found: {len(job_ads_list)}".center(60))
table_data = []

for index, job in enumerate(job_ads_list, 1):
    table_data.append([
        index,
        job.get("hiringOrgName", "-"),
        job.get("title", "—")[:40],
        f"{job.get('postalCode', '')} {job.get('postalDistrictName', '')}",
    ])

headres_table = ["#", "company", "position", "location"]
print(tabulate(table_data, headers=headres_table, tablefmt="rounded_grid"))
