#!/usr/bin/env python3
import sqlite3
import os

DB = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'poolparty.db')
print('DB file:', DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("PRAGMA table_info('pool')")
cols = [r[1] for r in cur.fetchall()]
print('Existing columns:', cols)
needed = {'origin_lat': 'FLOAT', 'origin_lng': 'FLOAT', 'dest_lat': 'FLOAT', 'dest_lng': 'FLOAT'}
added = []
for col, typ in needed.items():
    if col not in cols:
        try:
            cur.execute(f"ALTER TABLE pool ADD COLUMN {col} {typ}")
            print('Added column', col)
            added.append(col)
        except Exception as e:
            print('Failed to add', col, '->', e)
conn.commit()
conn.close()
if not added:
    print('No columns added (already present or failed)')
else:
    print('Added columns:', added)
