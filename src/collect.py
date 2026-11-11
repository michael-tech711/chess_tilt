# src/collect.py
import os, time
from pathlib import Path
import requests
from tqdm import tqdm

BASE = 'https://lichess.org'
RAW = Path('data/raw')
RAW.mkdir(parents=True, exist_ok=True)
SINCE_MS = 1704067200000        # 2024-01-01 UTC, change to taste

def download_user(username, max_games=3000, perf='blitz'):
    out = RAW / f'{username}.ndjson'
    if out.exists():
        return
    headers = {'Accept': 'application/x-ndjson'}
    if os.environ.get('LICHESS_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['LICHESS_TOKEN']
    params = {'rated': 'true', 'perfType': perf, 'since': SINCE_MS, 'max': max_games,
              'sort': 'dateAsc', 'clocks': 'true', 'opening': 'true',
              'accuracy': 'true', 'moves': 'true'}
    while True:
        r = requests.get(f'{BASE}/api/games/user/{username}', params=params,
                         headers=headers, stream=True, timeout=120)
        if r.status_code == 429:
            time.sleep(65)          # Lichess asks you to wait a minute
            continue
        r.raise_for_status()
        break
    tmp = out.with_suffix('.tmp')
    with open(tmp, 'wb') as f:
        for line in r.iter_lines():
            if line:
                f.write(line)
                f.write(b'\n')
    tmp.rename(out)

if __name__ == '__main__':
    names = open('data/usernames.txt').read().split()
    for n in tqdm(names):
        download_user(n)


