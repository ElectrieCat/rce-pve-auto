# Руководство преподавателя: учебные стенды на Proxmox VE

Инструмент: YAML-конфиги → Python → Terraform → Proxmox. Всё локально,
облачных зависимостей нет. Состояние — каталог `groups/` (там же Terraform state),
пароли — `passwords/*.csv` + `terraform.tfvars.json` в каталогах пользователей.

Требования: Linux, Python 3.10+, Terraform 1.x в PATH, доступ до Proxmox API (`:8006`).

## 1. Быстрый старт

```bash
pip install -r requirements.txt
cp -r configs-example configs
vim configs/auth.yaml      # endpoint + username/password (root@pam)
vim configs/users.yaml     # группа + студенты
vim configs/labs.yaml      # какая лаба какой группе
vim configs/labs/minimal-lab/main.yaml  # node/storage под свой кластер
# в configs/labs/minimal-lab/main.tf: clone.vm_id = ID своего шаблона
python main.py parse-test
python main.py status
python main.py deploy-users test-group --plan
python main.py deploy-users test-group
python main.py deploy-lab minimal-lab --plan
python main.py deploy-lab minimal-lab
python main.py backup
```

Раздача доступов студентам: `passwords/test-group.csv` (Username/Password).
Студенты ходят в Proxmox UI и видят только свой пул `test-group_Student1_minimal-lab`.

## 2. Ежедневные операции

### Посмотреть состояние

```bash
python main.py status
python main.py status --group test-group
python main.py status --lab minimal-lab
```

Состояния лабы: `deployed` (каталог + tfvars есть), `not-deployed`,
`skipped-unmanaged` (группа/юзер не описаны или `managed: false`),
`marked-destroy` (`destroy: true`).

### Создать группу / добавить студентов

1. Добавить группу/студентов в `configs/users.yaml`.
   `internal-id` — уникален среди ВСЕХ пользователей, назначается раз и навсегда
   (из него строятся имена мостов `u{id}l{lab}n{net}`; смена ID ломает сеть).
2. Если лаба должна быть и у новичков — добавить группу в `configs/labs.yaml`
   с `managed: true`.
3. `deploy-users <группа> --plan` → `deploy-users <группа>` → `deploy-lab <лаба>`.

Удаление студента из YAML + `deploy-users` убирает его из Proxmox,
НО только если у него нет каталогов лаб (orphan-protection). Сначала снесите его лабы.

### Развернуть стенд

```bash
python main.py deploy-lab minimal-lab --plan
python main.py deploy-lab minimal-lab
```

Отказ одному студенту без удаления: в `labs.yaml` для него `managed: false`.
Закрыть доступ, но оставить ВМ: `permit: false` (роль `NoAccess` вместо `PVEPoolUser`).

### Веб-обзор (опционально, только локально)

Тонкий UI поверх того же CLI: статус и `--plan`-превью в браузере.
Apply/destroy/смена паролей — только в терминале. Ядро не дублируется:
эндпоинты выполняют `python main.py ...` через subprocess.

```bash
pip install -r ui/requirements.txt
uvicorn ui.app:app --host 127.0.0.1 --port 8000   # только loopback, не 0.0.0.0!
# UI_READONLY=1 — режим дашборда без POST /api/run
```

`terraform-run` и `change-password` в UI не exposed.

### Удалить стенд (двухступенчато!)

```bash
python main.py backup
# в labs.yaml: destroy: true (группе или точечно юзеру)
python main.py destroy-lab minimal-lab --plan
python main.py destroy-lab minimal-lab   # ещё раз покажет план + попросит ввести destroy
# вернуть destroy: false
```

`managed: false` всегда имеет приоритет: такие каталоги `destroy-lab` не трогает,
их сносят вручную через `terraform-run --dir ... -- destroy` прямо в каталоге.

### Сменить пароль

Требует `username/password` в `auth.yaml` (API-токен пароли менять не умеет).

```bash
python main.py change-password test-group --user Student1  # спросит yes/no
python main.py change-password test-group                  # всей группе
```

Новый пароль — в `passwords/test-group.csv`. При фейле Terraform локальный файл
откатывается сам, CSV не перезаписывается.

### Ручные операции

```bash
# что реально есть в каталоге лабы
python main.py terraform-run --dir groups/test-group/users/Student1/labs/minimal-lab -- state list
# точечный план/применение мимо deploy-lab (уважает managed, кроме --force-managed)
python main.py terraform-run --lab minimal-lab --group test-group --user Student1 -- plan
```

## 3. Как добавить новый тип стенда

```bash
cp -r configs-example/labs/minimal-lab configs/labs/my-lab
```

1. `configs/labs/my-lab/main.yaml`: свои `nets:` (ключи — любые, они же ключи
   `module.base.bridge_names["<ключ>"]` в `main.tf`), `pve-locals.node/storage`,
   снапшоты (`create: true` требует имя + непустой `vm_snapshot_ids` в `main.tf`).
   `bridge-ports: ""` — изолированный мост; `"eth0"` — с аплинком (в кавычках!).
2. `main.tf`: блок `module "base"` не удалять (пул + сети + ACL).
   ВМ именовать с `${var.user_name}` (уникальность!), сеть брать из `module.base`.
   Клон от шаблона: `datastore_id` держать закомментированным (linked clone живёт
   на сторадже шаблона).
3. `variables.tf` / `providers.tf` — копировать как есть.
4. Зарегистрировать в `configs/labs.yaml` с новым уникальным `internal-id`
   (коллизия ID лаб = коллизия имён мостов). Группы, не перечисленные в лабе,
   её не получат — это норма, а не баг.
5. `deploy-lab my-lab --plan` → `deploy-lab my-lab`.

Вторая ВМ — просто второй `resource` + добавить её ID в `vm_snapshot_ids`, если нужны снапшоты.

## 4. Меры безопасности

- `--plan` перед каждым изменением; `destroy` — только через `destroy: true` + ввод слова.
- `python main.py backup` перед массовыми правками (архив `configs/`, `passwords/`, `groups/`).
- `configs/`, `passwords/`, `groups/` не коммитятся (уже в `.gitignore`) — там пароли
  в plaintext (`tfvars` + CSV). Лечите их как секреты: права `chmod 700`, без шаринга.
- API-токен не умеет менять пароли — для `change-password` нужен `root@pam` + пароль.
  Отдельного минимального юзера под инструмент в Proxmox заведите при первой возможности.
- `internal-id` юзеров и лаб не менять и не переиспользовать при живых стендах.
- `managed: false` — сейф для ручных доработок: инструмент каталог не тронет.
- `permit: false` скрывает пул, но не выключает ВМ — для нарушителей гасите ВМ отдельно.

## 5. Типичные проблемы

| Симптом | Причина → действие |
|---|---|
| `bridge_names["X"]` → empty/error | Ключ в `main.tf` не совпадает с `nets:` в `main.yaml`. Сверьте (`status` тут не поможет — смотрите текст ошибки Terraform). |
| Ошибка клонирования `vm_id` | Шаблона с таким ID нет на `pve-locals.node`. Проверьте ID/ноду. |
| Мост не создаётся (ports) | `bridge-ports` указывает на несуществующий интерфейс ноды. Для старта — `""`. |
| `change-password` → Permission/API token | Токены не меняют пароли → перейдите на `username/password` в `auth.yaml`. |
| `deploy-lab` всех скипает | Группа не перечислена в `labs.yaml` под этой лабой, либо `managed: false`. `status` покажет `skipped-unmanaged`. |
| `destroy-lab` «ничего не делает» | Нет `destroy: true` в `labs.yaml`, либо `managed: false` (приоритет выше). |
| Юзер не удаляется `deploy-users` | У него остались каталоги лаб → `[WARNING] active labs found`. Снесите лабы первым делом. |
| `terraform init` висит/401 | Неверный `endpoint`/креды в `auth.yaml`, самоподписанный серт при `insecure: false`. |
| Конфликт имён мостов между студентами | Дубли `internal-id` — инструмент ловит на старте (`[ERROR] Duplicate internal-id`), исправьте YAML до деплоя. |
| Потерян CSV с паролями | Пароли живут и в `groups/<g>/users/<u>/terraform.tfvars.json` — CSV перегенерируется следующим `deploy-users`/`change-password`. |

Не помогло — идите в каталог лабы (`groups/<группа>/users/<юзер>/labs/<лаба>/`)
и запускайте `terraform` напрямую через `terraform-run --dir ... -- <args>`.
