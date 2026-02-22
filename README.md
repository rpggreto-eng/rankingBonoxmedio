# 🏆 Sistema de Ranking - Setup Guide

## Instalación Rápida

```bash
pip install flask pillow pytesseract pandas openpyxl
python app.py
```

Luego abre: http://localhost:5000

---

## Estructura del Proyecto

```
ranking_system/
├── app.py              ← Aplicación principal (Flask)
├── requirements.txt    ← Dependencias
├── ranking.db          ← Base de datos SQLite (se crea automático)
└── templates/
    ├── base.html       ← Layout base
    ├── index.html      ← Página principal
    ├── register.html   ← Registro de usuarios
    ├── login.html      ← Inicio de sesión
    ├── profile.html    ← Perfil del jugador
    ├── ranking.html    ← Ranking completo
    ├── admin_login.html← Login de admins
    └── admin_dashboard.html ← Panel admin
```

---

## Cuentas de Admin

Hay **13 cuentas admin** preconfiguradas:
- **Usuarios:** admin1, admin2, admin3, ... admin13
- **Contraseña por defecto:** `Admin123!`

Para cambiar contraseñas, entra a SQLite:
```bash
python -c "
import sqlite3, hashlib
conn = sqlite3.connect('ranking.db')
new_pass = hashlib.sha256('TuNuevaContraseña'.encode()).hexdigest()
conn.execute(\"UPDATE admin_accounts SET password=? WHERE username=?\", (new_pass, 'admin1'))
conn.commit()
"
```

---

## Funcionalidades

### Usuarios
- ✅ Registro con: usuario, contraseña, Discord, Minecraft nick, email
- ✅ Login único por usuario/Discord/nick (no duplicados)
- ✅ Perfil con historial de puntos
- ✅ Ver ranking completo

### Admins
- ✅ 13 cuentas admin independientes
- ✅ Buscador rápido de jugadores (por usuario/discord/minecraft)
- ✅ Agregar puntos con: evento, posición, razón
- ✅ Auto-cálculo de puntos por posición (escala oficial)
- ✅ Historial/logs completo por usuario
- ✅ Crear eventos con nombre y fecha
- ✅ Asignación masiva (pegar lista posición,nick)
- ✅ OCR: subir imagen del ranking → detecta posiciones y nicks
- ✅ Exportar ranking a CSV (incluye Discord y Minecraft nick)

### Escala de Puntos
| Posición | Puntos |
|----------|--------|
| 1°       | 25 pts |
| 2°       | 15 pts |
| 3°       | 12 pts |
| 4°       | 10 pts |
| 5°-8°    | 5 pts  |
| 9°-15°   | 4 pts  |
| 16°-31°  | 3 pts  |
| 32°-64°  | 2 pts  |
| 65°-128° | 1 pt   |

---

## OCR (Captura de Pantalla → Ranking Automático)

Para usar la función OCR necesitas instalar **Tesseract-OCR** en el sistema:

**Windows:** https://github.com/UB-Mannheim/tesseract/wiki  
**Linux:** `sudo apt install tesseract-ocr tesseract-ocr-spa`  
**Mac:** `brew install tesseract`

Luego en Python: `pip install pytesseract pillow`

El OCR busca patrones como:
- `1. PlayerName`
- `#1 PlayerName`
- `1 PlayerName`

**Tip:** Funciona mejor con imágenes limpias y texto en blanco/negro.

---

## Producción

Para usar en producción:
1. Cambia `app.secret_key` en `app.py`
2. Cambia las contraseñas de admin
3. Usa gunicorn: `gunicorn -w 4 app:app`
4. Considera migrar a PostgreSQL para escala mayor

---

## Lógica de Nick Minecraft

- Al registrarse, el usuario ingresa su nick exacto
- Al asignar puntos masivos, se busca **case-insensitive**  
- Si el nick no está en la base de datos (ni en mayúsculas ni minúsculas), NO se asignan puntos
- Los nicks no encontrados se reportan en la sección "no_found"
