import psycopg2
from db_config import DB_CONFIG
conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

# Cohen & Steers(CNS) 오매칭 삭제
cur.execute("SELECT id FROM tickers WHERE symbol = 'CNS'")
cns_id = cur.fetchone()[0]
cur.execute("DELETE FROM post_mentions WHERE ticker_id = %s", (cns_id,))
print(f"post_mentions 삭제: {cur.rowcount}건")
cur.execute("DELETE FROM expert_article_mentions WHERE ticker_id = %s", (cns_id,))
print(f"expert_article_mentions 삭제: {cur.rowcount}건")

conn.commit()
conn.close()
print("완료")
