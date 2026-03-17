# Despliegue en Render con PostgreSQL

Esta app ahora soporta almacenamiento en base de datos usando la variable `DATABASE_URL`.

Si `DATABASE_URL` existe, guarda `config`, `state`, `checklist` e `inventory_history` en PostgreSQL.
Si no existe, usa archivos JSON locales como antes.

## 1) Subir el proyecto a GitHub

1. Crea un repositorio en GitHub.
2. Sube el contenido de este proyecto.

## 2) Crear base de datos PostgreSQL en Render

1. En Render: `New +` -> `PostgreSQL`.
2. Pon nombre (ej: `mant-v2-db`) y crea la DB.
3. Cuando termine, copia el valor de `External Database URL`.

## 3) Crear el Web Service en Render

1. En Render: `New +` -> `Web Service`.
2. Conecta tu repositorio de GitHub.
3. Configura:
   - **Root Directory**: `web`
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## 4) Variables de entorno

En el Web Service, en `Environment`, agrega:

- `DATABASE_URL` = (External Database URL de Render Postgres)
- `glpi_url`
- `glpi_app_token`
- `glpi_user_token`
- `glpi_category_id` (opcional)
- `glpi_field_id` (opcional)
- `azure_client_id` (si usas Outlook)
- `azure_client_secret` (si usas Outlook)
- `azure_tenant_id` (si usas Outlook)
- `outlook_calendar_id` (opcional)
- `outlook_user_upn` (si usas Outlook)
- `notify_emails` (opcional)

Nota: también puedes configurar estos valores desde la UI en `/api/config`, pero en Render es mejor manejar secretos por variables.

## 5) Verificar

1. Abre la URL del Web Service.
2. Verifica salud en: `/api/health`
3. Debe mostrar:
   - `"status": "ok"`
   - `"db_enabled": true`
   - `"db_backend": "postgres"`

## 6) Migración desde JSON local (automática)

La primera vez que la app lee una clave y detecta archivo JSON local, la sube a DB automáticamente.
Esto aplica para:

- `config.json`
- `state.json`
- `checklist.json`
- `inventory_history.json`

## 7) Conexión desde DBeaver

Conéctate a la misma PostgreSQL de Render con:

- Host
- Port
- Database
- Username
- Password

Estos datos están en la pantalla de la base de datos en Render.

La tabla usada por la app es:

- `app_kv`

Columnas:

- `k` (clave)
- `v` (json serializado)
- `updated_at`

