# src/features.py

import json
from pathlib import Path
import numpy as np
import pandas as pd

def parse_game(g, username):
    if 'tournament' in g or 'swiss' in g:       # arena/swiss games behave differently
        return None
    if g.get('status') in ('aborted', 'noStart'):
        return None
    players = g['players']
    me_color = None
    for color in ('white', 'black'):
        u = players[color].get('user')
        if u and u['name'].lower() == username.lower():
            me_color = color
    if me_color is None:
        return None
    opp_color = 'black' if me_color == 'white' else 'white'
    me, opp = players[me_color], players[opp_color]
    if 'rating' not in me or 'rating' not in opp:
        return None

    winner = g.get('winner')
    if winner is None and g.get('status') not in ('draw', 'stalemate'):
        return None                                # unknown result
    score = 0.5 if winner is None else (1.0 if winner == me_color else 0.0)
    expected = 1 / (1 + 10 ** ((opp['rating'] - me['rating']) / 400))

    # clock features (centiseconds)
    clk = g.get('clock') or {}
    init, inc = clk.get('initial', 0) * 100, clk.get('increment', 0) * 100
    clocks = g.get('clocks') or []
    mine = clocks[0::2] if me_color == 'white' else clocks[1::2]
    prev = [init] + mine[:-1]
    spent = [p + inc - c for p, c in zip(prev, mine)]
    early = spent[2:12]                           # skip the first two moves
    early_move_time = np.mean(early) / 100 if len(early) >= 5 else np.nan
    time_trouble = int(min(mine) < 0.1 * init) if mine and init else np.nan

    ana = me.get('analysis') or {}
    return {
        'player_id': username.lower(), 'game_id': g['id'],
        'start_ms': g['createdAt'], 'end_ms': g['lastMoveAt'],
        'color': me_color, 'own_rating': me['rating'], 'opp_rating': opp['rating'],
        'rating_diff': opp['rating'] - me['rating'],
        'score': score, 'expected': expected, 'resid': score - expected,
        'status': g.get('status'), 'n_plies': len((g.get('moves') or '').split()),
        'early_move_time': early_move_time, 'time_trouble': time_trouble,
        'accuracy': ana.get('accuracy'), 'acpl': ana.get('acpl'),
        'blunders': ana.get('blunder'),
        'eco': (g.get('opening') or {}).get('eco'),
    }

def load_all(raw_dir='data/raw'):
    rows = []
    for f in Path(raw_dir).glob('*.ndjson'):
        username = f.stem
        with open(f, encoding='utf-8') as fh:
            for line in fh:
                if not line.strip():
                    continue
                r = parse_game(json.loads(line), username)
                if r:
                    rows.append(r)
    return pd.DataFrame(rows)

def add_sequence_features(df, gap_minutes=30):
    df = df.sort_values(['player_id', 'start_ms']).reset_index(drop=True)
    gap = (df['start_ms'] - df.groupby('player_id')['end_ms'].shift(1)) / 60000
    new_session = gap.isna() | (gap > gap_minutes)
    df['session_id'] = new_session.cumsum()

    s = df.groupby('session_id')
    df['game_no'] = s.cumcount()
    df['game_no_cap'] = df['game_no'].clip(upper=15)
    df['gap_min'] = gap.where(df['game_no'] > 0)
    df['prev_score'] = s['score'].shift(1)
    df['lost_prev'] = (df['prev_score'] == 0).astype(int)
    df['drew_prev'] = (df['prev_score'] == 0.5).astype(int)

    # consecutive losses entering this game
    lost = (df['score'] == 0).astype(int)
    block = (lost == 0).groupby(df['session_id']).cumsum()
    run = lost.groupby([df['session_id'], block]).cumsum()
    df['streak_in'] = run.groupby(df['session_id']).shift(1).fillna(0)
    df['streak_bucket'] = df['streak_in'].clip(upper=3).astype(int)

    df['hour'] = pd.to_datetime(df['start_ms'], unit='ms').dt.hour   # UTC, a rough control
    return df

if __name__ == '__main__':
    df = add_sequence_features(load_all())
    Path('data/processed').mkdir(parents=True, exist_ok=True)
    df.to_parquet('data/processed/games.parquet')
    print(len(df), 'games,', df['player_id'].nunique(), 'players,',
          df['session_id'].nunique(), 'sessions')