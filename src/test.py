import pandas as pd

df = pd.read_parquet('data/processed/games.parquet')

print(df.shape)          # (rows, columns)
print(df.head(10))         # first 5 games
print(df.dtypes)         