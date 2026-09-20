import concurrent.futures as cf

# import requests
from tabulate import tabulate
from sources.cache import fetch as cached

QUERY = "address=Sj%C3%A6llandsgade+40%2C+2200+K%C3%B8benhavn+N&latitude=55.695568353727&longitude=12.557425020522&radius=10&sort=score"
BASE  = "https://www.jobindex.dk/api/jobsearch/v3/?"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
}
WORKERS = 8


def _fetch(page):
    # r = requests.get(f"{BASE}{QUERY}&page={page}", headers=HEADERS, timeout=30)
    # r.raise_for_status()
    # return r.json()
    url = f"{BASE}{QUERY}&page={page}"
    return cached(url, HEADERS)

# first = fetch(1)
# pages = min(first["total_pages"], first["max_page"])
# results = first["results"]

def get_jobs():
    first = _fetch(1)
    pages = min(first["total_pages"], first["max_page"])
    jobs = list(first["results"])

    with cf.ThreadPoolExecutor(WORKERS) as pool:
        for data in pool.map(_fetch, range(2, pages + 1)):
            jobs += data["results"]
    return jobs 

def main():
    jobs = get_jobs()

    table_data = [
        [i, j.get("companytext") or j["company"]["name"], j["headline"][:40], j.get("area", "")]
        for i, j in enumerate(jobs, 1)
    ]
    print(f" found: {len(jobs)}".center(60))
    print(tabulate(table_data, headers=["#", "company", "position", "location"], tablefmt="rounded_grid"))


"""
with cf.ThreadPoolExecutor(8) as pool:
    # for url, ads in zip(urls, pool.map(fetch, urls)):
    #     print(url)
    #     print(len(ads))
    #     for job in ads:
    #         job_id = job.get("jobAdId")
    #         if job_id not in seen_ids:
    #             seen_ids.add(job_id)
    #             job_ads_list.append(job)
    for data in pool.map(
        fetch, range(2, pages+1)
    ):
        results += data["results"]

seen, jobs = set(), []
for job in results:
    if job["tid"] not in seen:
        seen.add(job["tid"])
        jobs.append(job)



print(f" found: {len(jobs)}".center(60))
table_data = [
    [
        i,
        job.get("companytext") or job["company"]["name"],
        job["headline"][:40],
        job["area"]
    ]
    for i, job in enumerate(jobs, 1)
]

# for index, job in enumerate(job_ads_list, 1):
#     table_data.append([
#         index,
#         job.get("hiringOrgName", "-"),
#         job.get("title", "—")[:40],
#         f"{job.get('postalCode', '')} {job.get('postalDistrictName', '')}",
#     ])

headres_table = ["#", "company", "position", "location"]
print(tabulate(table_data, headers=headres_table, tablefmt="rounded_grid"))
"""