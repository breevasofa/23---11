#!/usr/bin/env bash
set -euo pipefail

export DISPLAY=:99
mkdir -p titanic_w_p/screenshots
Xvfb :99 -screen 0 1600x900x24 >/tmp/titanic_xvfb.log 2>&1 &
sleep 1

xterm -T 'GitHub Actions workspace - Titanic W/P - code 1' \
  -geometry 155x47+12+12 -fa 'DejaVu Sans Mono' -fs 11 \
  -bg '#1e1e1e' -fg '#e8e8e8' -hold \
  -e bash -lc 'printf "$ nl -ba titanic_w_p/analysis.py | sed -n '\''1,74p'\''\n\n"; nl -ba titanic_w_p/analysis.py | sed -n "1,74p"' &
sleep 2
scrot titanic_w_p/screenshots/01_code_sets.png

xterm -T 'GitHub Actions workspace - Titanic W/P - code 2' \
  -geometry 155x47+12+12 -fa 'DejaVu Sans Mono' -fs 11 \
  -bg '#1e1e1e' -fg '#e8e8e8' -hold \
  -e bash -lc 'printf "$ nl -ba titanic_w_p/analysis.py | sed -n '\''75,140p'\''\n\n"; nl -ba titanic_w_p/analysis.py | sed -n "75,140p"' &
sleep 2
scrot titanic_w_p/screenshots/02_code_scoring.png

xterm -T 'GitHub Actions workspace - Titanic W/P - results' \
  -geometry 155x47+12+12 -fa 'DejaVu Sans Mono' -fs 11 \
  -bg '#1e1e1e' -fg '#e8e8e8' -hold \
  -e bash -lc 'printf "$ python titanic_w_p/analysis.py\n\n"; python titanic_w_p/analysis.py' &
sleep 6
scrot titanic_w_p/screenshots/03_results.png

test "$(find titanic_w_p/screenshots -name '*.png' | wc -l)" = 3
