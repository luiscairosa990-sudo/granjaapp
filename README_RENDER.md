# GranjaApp - Para Render.com

## Deploy en Render

1. Comprime esta carpeta en un ZIP (sin la base de datos granja.db)
2. Ve a render.com → New + → Web Service
3. Selecciona "Upload your code" y sube el ZIP
4. Configura:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
5. En "Environment Variables" agrega:
   - `SECRET_KEY` = cualquier texto largo y seguro
6. Click en "Create Web Service"

## Credenciales por defecto
- admin / 1234
- operario / 1234

## Notas
- La base de datos SQLite se crea automáticamente en Render
- Para producción real, considera usar PostgreSQL
