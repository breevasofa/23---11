"""Загрузить организации с более чем 10 предписаниями в Redis."""

from __future__ import annotations

import argparse
import json
import uuid
from decimal import Decimal

import pandas as pd
import redis


SOURCE_URL = (
    "https://github.com/junaart/ForStudents/raw/refs/heads/main/Big_Data/"
    "data_%D0%A3%D0%9A.xlsx"
)
ORGANIZATION = "Наименование управляющей организации, жилищного объединения"
PRESCRIPTIONS = "Выдано предписаний"
SOURCE_FINE = "Сумма штрафа (тыс. руб.)"
REDIS_FINE = "Сумма штрафов"
KEY_PREFIX = "uk:org:"


def select_organizations(source: str) -> tuple[int, dict[str, dict[str, str]]]:
    frame = pd.read_excel(source, engine="openpyxl")
    required = {ORGANIZATION, PRESCRIPTIONS, SOURCE_FINE}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"В Excel нет столбцов: {', '.join(sorted(missing))}")

    counts = pd.to_numeric(frame[PRESCRIPTIONS], errors="raise")
    selected = frame.loc[counts.gt(10), [ORGANIZATION, PRESCRIPTIONS, SOURCE_FINE]].copy()
    if selected[ORGANIZATION].isna().any():
        raise ValueError("У выбранной организации отсутствует наименование")

    selected[ORGANIZATION] = selected[ORGANIZATION].astype(str).str.strip()
    if selected[ORGANIZATION].eq("").any():
        raise ValueError("У выбранной организации пустое наименование")
    if selected[ORGANIZATION].duplicated().any():
        raise ValueError("Повторяются наименования организаций: запись может быть потеряна")

    fines = pd.to_numeric(selected[SOURCE_FINE], errors="raise")
    if fines.isna().any():
        raise ValueError("У выбранной организации отсутствует сумма штрафов")

    records: dict[str, dict[str, str]] = {}
    for name, count, fine in zip(
        selected[ORGANIZATION], selected[PRESCRIPTIONS], fines, strict=True
    ):
        if int(count) != count:
            raise ValueError(f"Число предписаний не целое: {name}")
        key = KEY_PREFIX + str(uuid.uuid5(uuid.NAMESPACE_URL, name))
        records[key] = {
            "Организация": name,
            PRESCRIPTIONS: str(int(count)),
            REDIS_FINE: format(Decimal(str(fine)), "f"),
        }
    return len(frame), records


def save_and_verify(client: redis.Redis, records: dict[str, dict[str, str]]) -> None:
    client.ping()
    with client.pipeline(transaction=False) as pipe:
        for key, fields in records.items():
            pipe.hset(key, mapping=fields)
        pipe.execute()

    keys_in_redis = set(client.scan_iter(match=KEY_PREFIX + "*"))
    if keys_in_redis != set(records):
        raise RuntimeError("Набор хэшей Redis не совпадает с выбранными организациями")

    with client.pipeline(transaction=False) as pipe:
        for key in records:
            pipe.hgetall(key)
        saved = pipe.execute()
    for (key, expected), actual in zip(records.items(), saved, strict=True):
        if actual != expected:
            raise RuntimeError(f"Содержимое хэша не совпадает с Excel: {key}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=SOURCE_URL, help="URL или путь к файлу Excel")
    args = parser.parse_args()

    total, records = select_organizations(args.source)
    client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    save_and_verify(client, records)

    example_key, example = max(
        records.items(), key=lambda item: int(item[1][PRESCRIPTIONS])
    )
    print(f"Всего строк в Excel: {total}")
    print(f"Организаций с предписаниями > 10: {len(records)}")
    print(f"Хэшей в Redis проверено: {len(records)}")
    print(f"Пример ключа: {example_key}")
    print("Пример хэша: " + json.dumps(example, ensure_ascii=False))


if __name__ == "__main__":
    main()
