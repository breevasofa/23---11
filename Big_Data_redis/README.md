# Организации с более чем 10 предписаниями в Redis

Скрипт читает [исходный Excel-файл](https://github.com/junaart/ForStudents/raw/refs/heads/main/Big_Data/data_%D0%A3%D0%9A.xlsx), выбирает строки, где `Выдано предписаний > 10`, и сохраняет каждую организацию отдельным хэшем Redis. В исходном файле 32 007 строк; условию соответствуют 1 343 организации. Наименования в этой выборке уникальны.

Каждый ключ имеет вид `uk:org:<UUID>`. UUID создаётся из полного названия организации, поэтому повторный запуск обновляет тот же хэш. Поля хэша: `Организация`, `Выдано предписаний`, `Сумма штрафов`. Сумма штрафов сохранена в **тысячах рублей**, как в Excel. После загрузки скрипт повторно читает все 1 343 хэша и сравнивает их с данными файла.

## Запуск в GitHub Codespaces

Конфигурация `.devcontainer/devcontainer.json` включает расширения Python и Jupyter для VS Code, устанавливает Python-библиотеки и запускает Redis при старте контейнера. В уже созданном Codespace после обновления репозитория выполните команду **Codespaces: Rebuild Container**. Для нового Codespace конфигурация применяется при создании.

В терминале Codespaces из корня репозитория выполните:

```bash
python Big_Data_redis/load_to_redis.py
redis-cli --raw ping
redis-cli --scan --pattern 'uk:org:*' | wc -l
redis-cli --raw HGETALL "$(redis-cli --scan --pattern 'uk:org:*' | sort | sed -n '1p')"
```

Ожидаемые количества: 32 007 строк Excel и 1 343 хэша Redis. Redis доступен только через `localhost:6379`; его данные сохраняются в игнорируемой Git папке `Big_Data_redis/.redis-data` внутри Codespace. Workflow GitHub Actions запускает те же проверки при изменении решения и позволяет увидеть вывод Python и `redis-cli` в GitHub.
