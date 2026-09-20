import concurrent.futures as cf
import html
import re
from sources.cache import fetch_text

HEADERS =  {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TTL = 7 * 24 * 3600
WORKERS = 8


JOBANNONCE = re.compile(r'href="(https://www\.jobindex\.dk/jobannonce/[^"]+)"[^>]*>Se jobbet')
BODY_STOP = ("Lignende job", "Om virksomheden", "jix-info", "Del annoncen")
TEASER_STOP = ("Om virksomheden", "Lignende job", "Del annoncen", "Indrykket:", "Følger", "Gem job", "Ansøg", "Se jobbet")

def _text(chunk):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", chunk))).strip()




def _cut(page, start, markers):
    end = len(page)
    for marker in markers:
        i = page.find(marker, start)
        if i != -1:
            end = min(end, i)
    return _text(page[start:end])


def _teaser(page):
    i = page.find("<p>")
    if i != -1:
        text = _cut(page, i, TEASER_STOP)
        if text:
            return text
    og = re.search(r'property="og:description"[^>]*content="([^"]*)"', page)
    if not og:
        og = re.search(r'content="([^"]*)"[^>]*property="og:description"', page)
    return _text(og.group(1)) if og else ""


def _body(page):
    h1 = re.search(r"<h1[^>]*>.*?</h1>", page, re.S)
    return _cut(page, h1.end() if h1 else 0, BODY_STOP)



def _description(job):
    try:
        page = fetch_text(job["url"], HEADERS, ttl=TTL)
        m = JOBANNONCE.search(page)
        if m:
            full = _body(fetch_text(html.unescape(m.group(1)), HEADERS, ttl=TTL))
            if len(full) > 400:
                return full
        return _teaser(page)
    except Exception as e:
        print(f"enrich fail {job['id']}: {e}")
        return job["description"] or job["title"]


def enrich_jobindex(jobs):
    targets = [j for j in jobs if j["source"] == "jobindex"]
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        for i, (job, text) in enumerate(zip(targets, pool.map(_description, targets)), 1):
            job["description"] = text or job["title"]
            if i % 200 == 0:
                print(f"enriched {i}/{len(targets)}")
    return jobs