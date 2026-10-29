"""Отбор организаций из Excel и сохранение двух показателей в Redis HASH."""

from decimal import Decimal
from pathlib import Path

import pandas as pd
import redis


SOURCE = (
    "https://github.com/junaart/ForStudents/raw/refs/heads/main/Big_Data/"
    "data_%D0%A3%D0%9A.xlsx"
)
ORGANIZATION = "Наименование управляющей организации, жилищного объединения"
PRESCRIPTIONS = "Выдано предписаний"
SOURCE_FINE = "Сумма штрафа (тыс. руб.)"
REDIS_FINE = "Сумма штрафов"


def main() -> None:
    frame = pd.read_excel(SOURCE, engine="openpyxl")
    counts = pd.to_numeric(frame[PRESCRIPTIONS], errors="raise")
    selected = frame.loc[
        counts > 10, [ORGANIZATION, PRESCRIPTIONS, SOURCE_FINE]
    ].copy()

    if selected[ORGANIZATION].isna().any():
        raise ValueError("У выбранной организации нет названия")
    selected[ORGANIZATION] = selected[ORGANIZATION].astype(str).str.strip()
    if selected[ORGANIZATION].eq("").any() or selected[ORGANIZATION].duplicated().any():
        raise ValueError("Пустое или повторяющееся название организации")

    fines = pd.to_numeric(selected[SOURCE_FINE], errors="raise")
    if fines.isna().any():
        raise ValueError("У выбранной организации нет суммы штрафов")

    # Ключ Redis — полное название организации. Значение — HASH из двух полей.
    hashes: dict[str, dict[str, str]] = {}
    for name, count, fine in zip(
        selected[ORGANIZATION], selected[PRESCRIPTIONS], fines, strict=True
    ):
        if int(count) != count:
            raise ValueError(f"Нецелое число предписаний: {name}")
        hashes[name] = {
            PRESCRIPTIONS: str(int(count)),
            REDIS_FINE: format(Decimal(str(fine)), "f"),
        }

    client = redis.Redis(host="localhost", port=6379, db=0, decode_responses=True)
    client.ping()
    with client.pipeline(transaction=False) as pipe:
        for name, fields in hashes.items():
            pipe.hset(name, mapping=fields)
        pipe.execute()

    # Проверяем полный набор ключей, тип и оба значения каждого хэша.
    if set(client.scan_iter()) != set(hashes):
        raise AssertionError("Набор ключей Redis не совпал с выборкой Excel")
    with client.pipeline(transaction=False) as pipe:
        for name in hashes:
            pipe.type(name)
            pipe.hgetall(name)
        saved = pipe.execute()
    for index, (name, fields) in enumerate(hashes.items()):
        if saved[2 * index] != "hash" or saved[2 * index + 1] != fields:
            raise AssertionError(f"Ошибка проверки хэша: {name}")

    example = max(hashes, key=lambda name: int(hashes[name][PRESCRIPTIONS]))
    Path(__file__).with_name("sample_key.txt").write_text(example, encoding="utf-8")
    print(f"Строк в Excel: {len(frame)}")
    print(f"Организаций с предписаниями > 10: {len(hashes)}")
    print(f"Проверено Redis HASH: {len(hashes)}")
    print(f"Пример ключа (название организации):\n{example}")
    print(f"Пример HGETALL: {client.hgetall(example)}")


if __name__ == "__main__":
    main()
