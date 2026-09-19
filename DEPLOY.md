# Деплой на постоянный сайт (Streamlit Community Cloud)

Ссылка вида `https://<имя>.streamlit.app` работает 24/7, не зависит от вашего
компьютера и провайдера. Бесплатно.

## Шаг 1. Создайте репозиторий на GitHub

1. Зарегистрируйтесь/войдите на https://github.com
2. Нажмите **New repository** → имя `fuel-cosmos-2035` → **Public** → Create
3. GitHub покажет команды загрузки — используйте их из папки проекта:

```powershell
cd C:\Users\Анастасия\Desktop\ter
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" remote add origin https://github.com/<ВАШ_ЛОГИН>/fuel-cosmos-2035.git
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" push -u origin main
```

GitHub запросит логин/пароль — вводите логин и **Personal Access Token**
(создаётся: GitHub → Settings → Developer settings → Personal access tokens →
Generate new token (classic) → отметьте `repo`). Пароль от аккаунта не подойдёт.

Перед пушем поменяйте подпись коммитов на свою (один раз):

```powershell
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" config user.name "Ваше Имя"
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" config user.email "ваш@email"
```

(текущая подпись в репозитории — временная заглушка; можно также перезаписать:
`git commit --amend --reset-author`)

## Шаг 2. Задеплойте на Streamlit Cloud

1. Откройте https://share.streamlit.io и войдите через аккаунт GitHub
2. **Create app** → **Deploy a public app from GitHub**
3. Заполните:
   - Repository: `<ВАШ_ЛОГИН>/fuel-cosmos-2035`
   - Branch: `main`
   - Main file path: `src/fuelloop/app/dashboard.py`
   - App URL: придумайте имя, например `fuel-cosmos-2035`
4. Нажмите **Deploy** — через 3–5 минут приложение соберётся и откроется:
   `https://fuel-cosmos-2035.streamlit.app`

Зависимости возьмутся из `requirements.txt`, данные — из `data/` и `configs/`
репозитория, ничего дополнительно настраивать не нужно.

## Обновление сайта

Любой push в `main` автоматически перезапускает приложение:

```powershell
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" add -A
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" commit -m "обновление"
& "C:\Users\08DE~1\AppData\Local\Temp\opencode\mingit\cmd\git.exe" push
```

## Тот же репозиторий на GitVerse (требование кейса)

1. Зарегистрируйтесь на https://gitverse.ru → Создать репозиторий `fuel-cosmos-2035`
2. Добавьте второй remote и запушьте:

```powershell
& "...git.exe" remote add gitverse https://gitverse.ru/<ЛОГИН>/fuel-cosmos-2035.git
& "...git.exe" push -u gitverse main
```

## Быстрая публичная ссылка (демо, без деплоя)

Запустите `scripts\start_public.bat` — выдаст временную ссылку trycloudflare.com.
Внимание: у вашего провайдера нестабилен канал Cloudflare (порт 7844), ссылка
может пропадать на минуты — для жюри используйте streamlit.app.
