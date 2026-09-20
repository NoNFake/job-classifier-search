import csv
import json
from pathlib import Path

from jobfit import load_jobs, score_key

SCORES = Path(".cache/scores.json")
OUT = Path("labels.csv")
TOP = 200


def main():
    cache = json.loads(SCORES.read_text()) if SCORES.exists() else {}
    jobs = [j for j in load_jobs() if score_key(j) in cache]
    jobs.sort(key=lambda j: cache[score_key(j)]["final_percent"], reverse=True)

    with OUT.open("w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "key", "title", "company", "location", "url", "match",
            "human_skill_overlap", "human_role_fit", "human_spam",
        ])
        for job in jobs[:TOP]:
            writer.writerow([
                score_key(job), job["title"], job["company"], job["location"], job["url"],
                cache[score_key(job)]["final_percent"], "", "", "",
            ])
    print(f"wrote {min(len(jobs), TOP)} rows -> {OUT}")
    print("fill human_skill_overlap (0-4), human_role_fit (0-4), human_spam (0 or 1)")


if __name__ == "__main__":
    main()
