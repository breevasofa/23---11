#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p 'Лабораторная работа №1!' 'ФИО'
: > 'Text @1'
: > 'Text $2'
: > 'Text #3'

printf '%s\n' \
  'Птица говорун отличается умом и сообразительностью!' \
  'Отличается умом, отличается сообразительностью...' > 'Text @1'

cp 'Text @1' 'Text $2'
mv 'Text $2' 'Лабораторная работа №1!/'
cp 'Text @1' 'ФИО/'

head -n 1 'Text @1' > 'Text #3'
printf '%s\n' 'Будь осторожен! Преступник вооружен!' >> 'Text #3'

tac 'Text @1' > 'ФИО/Result_one'
mv 'ФИО/Result_one' 'ФИО/Result_two'

{
  uname -a
  date '+%Y-%m-%d %H:%M:%S %Z'
} >> 'Result_3'

# Права задаются последними, иначе в каталог «ФИО» нельзя записать файлы.
chmod 772 'Лабораторная работа №1!'
chmod 200 'ФИО'
