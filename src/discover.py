# src/discover.py

import os, json, random
import requests
import time

BASE = 'https://lichess.org'
TOKEN = os.environ.get('LICHESS_TOKEN')
SINCE_MS = 1704067200000
USER_AGENT = 'chess-tilt-project (Kiem_67)'

def _headers(accept):
    # all discovery endpoints are public, and a token without team:read breaks the team one
    return {'Accept': accept, 'User-Agent': USER_AGENT}

def top_players(n=100, perf='blitz'):
    r = requests.get(f'{BASE}/api/player/top/{n}/{perf}',
                     headers=_headers('application/json'), timeout=30)
    r.raise_for_status()
    return [u['username'] for u in r.json()['users']]

def team_member_ids(team_id, max_scan=3000):
    ids = []
    with requests.get(f'{BASE}/api/team/{team_id}/users',
                      headers=_headers('application/x-ndjson'),
                      stream=True, timeout=60) as r:
        r.raise_for_status()
        for i, line in enumerate(r.iter_lines()):
            if i >= max_scan:
                break
            if line:
                ids.append(json.loads(line)['id'])
    return ids

def blitz_stats(ids):
    """Return {username: blitz_games} using the bulk users endpoint."""
    stats = {}
    for i in range(0, len(ids), 300):
        chunk = ids[i:i + 300]
        h = _headers('application/json')
        h['Content-Type'] = 'text/plain'
        r = requests.post(f'{BASE}/api/users', data=','.join(chunk),
                          headers=h, timeout=60)
        r.raise_for_status()
        for u in r.json():
            if u.get('disabled') or u.get('tosViolation'):
                continue
            if u.get('seenAt', 0) < SINCE_MS:
                continue
            blitz = (u.get('perfs') or {}).get('blitz') or {}
            stats[u['username']] = blitz.get('games', 0)
    return stats

def has_recent_games(username, perf='blitz'):
    """True if the games endpoint returns at least one game in our window."""
    for _ in range(3):
        r = requests.get(f'{BASE}/api/games/user/{username}',
                         params={'rated': 'true', 'perfType': perf,
                                 'since': SINCE_MS, 'max': 1},
                         headers=_headers('application/x-ndjson'), timeout=30)
        if r.status_code == 429:
            time.sleep(65)
            continue
        print(f'  {username}: HTTP {r.status_code}, {len(r.text)} bytes', flush=True)
        return r.status_code == 200 and bool(r.text.strip())
    return False

def team_users(team_id, n_sample=30, min_blitz_games=500,
               max_scan=3000, pool=200, seed=42):
    rng = random.Random(seed)
    ids = team_member_ids(team_id, max_scan)
    candidates = rng.sample(ids, min(pool, len(ids)))
    stats = blitz_stats(candidates)
    qualifying = [name for name, g in stats.items() if g >= min_blitz_games]
    rng.shuffle(qualifying)

    kept = []
    for name in qualifying:
        if has_recent_games(name):
            kept.append(name)
            if len(kept) == n_sample:
                break
        time.sleep(0.5)
    print(f'{team_id}: scanned {len(ids)}, checked {len(candidates)}, '
          f'{len(qualifying)} qualify, {len(kept)} verified')
    return kept

if __name__ == '__main__':
    rng = random.Random(42)
    names = set(rng.sample(top_players(100), 10))      # a few top players only
    for team in ['lichess-swiss', 'online-world-chess-lovers']:
        names.update(team_users(team, n_sample=60, pool=300, max_scan=5000))
    os.makedirs('data', exist_ok=True)
    open('data/usernames.txt', 'w').write(' '.join(sorted(names)))
    print(len(names), 'usernames')