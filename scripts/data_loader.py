"""
데이터 로더 - CSV 파일에서 별칭, 오매칭 방지, 감성 키워드 로드
crawler_config.py의 정적 설정과 분리하여 로딩 로직을 관리
"""

import csv
import os

_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def load_aliases() -> dict:
    """aliases.csv → {alias: symbol}"""
    path = os.path.join(_DATA_DIR, "aliases.csv")
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result[row["alias"].strip()] = row["symbol"].strip()
    return result


def load_multi_aliases() -> dict:
    """multi_aliases.csv → {alias: [symbol, ...]}"""
    path = os.path.join(_DATA_DIR, "multi_aliases.csv")
    result = {}
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            alias = row["alias"].strip()
            symbols = [s.strip() for s in row["symbols"].split(",")]
            result[alias] = symbols
    return result


def load_skip_names() -> set:
    """skip_names.csv → set"""
    path = os.path.join(_DATA_DIR, "skip_names.csv")
    result = set()
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            result.add(row["name"].strip())
    return result


def load_sentiment_words() -> tuple[list, list]:
    """sentiment_words.csv → (positive_list, negative_list)"""
    path = os.path.join(_DATA_DIR, "sentiment_words.csv")
    positive, negative = [], []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            word = row["word"].strip()
            if row["sentiment"].strip() == "positive":
                positive.append(word)
            elif row["sentiment"].strip() == "negative":
                negative.append(word)
    return positive, negative
