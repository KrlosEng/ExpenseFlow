# ExpenseFlow

Una aplicación web para llevar tus finanzas personales del mes: cuánto entró, cuánto salió, en qué se fue, cuánto te queda en cada presupuesto, cómo van tus metas de ahorro y qué suscripciones te van a cobrar.

[![CI](https://github.com/KrlosEng/ExpenseFlow/actions/workflows/ci.yml/badge.svg)](https://github.com/KrlosEng/ExpenseFlow/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![Licencia](https://img.shields.io/badge/Licencia-MIT-informational)

![Resumen del mes en ExpenseFlow](docs/screenshots/resumen-claro.png)

## Qué hace

- **Resumen del mes.** Lo que te queda, lo que entró y salió, en qué categorías se fue el dinero, el gasto por día, los presupuestos más justos y los próximos cobros. Arriba, una frase con lo más importante del mes.
- **Movimientos.** Registra, edita y elimina ingresos y gastos. Busca, filtra por fecha, tipo o categoría y recorre la lista por páginas.
- **Presupuestos por categoría.** Límite mensual con el gasto real del mes y alertas cuando llegas al 80 % o te pasas.
- **Metas de ahorro.** Cuánto llevas, cuánto falta y para cuándo. Cada abono queda registrado como movimiento.
- **Suscripciones.** Cuando llega la fecha de cobro, el gasto se registra solo y la próxima fecha avanza un mes o un año. Se pueden pausar.
- **Calculadora de cuotas.** Calcula la cuota mensual de una compra a plazos (sistema francés) y registra la primera cuota.
- **Importar y exportar.** Exporta a CSV e importa CSV (el exportado, o uno con columnas Fecha, Concepto, Monto, Tipo y Categoría) o JSON.
- **Cuentas de usuario.** Registro e inicio de sesión; cada persona ve solo sus datos.
- **Moneda.** Pesos colombianos por defecto (`$ 4.800.000`); también USD, EUR y MXN.
- **Modo claro y oscuro**, versión para teléfono y navegación con teclado.

| Movimientos | Teléfono |
| :--- | :--- |
| ![Lista de movimientos](docs/screenshots/movimientos.png) | ![Resumen en el teléfono](docs/screenshots/telefono.png) |

| Presupuestos | Modo oscuro |
| :--- | :--- |
| ![Presupuestos del mes](docs/screenshots/presupuestos.png) | ![Resumen en modo oscuro](docs/screenshots/resumen-oscuro.png) |

## Tecnología

- **Backend:** Python 3.10+, FastAPI y Pydantic. SQLite en local y PostgreSQL en producción, según `DATABASE_URL`.
- **Autenticación:** contraseñas con scrypt y sesión JWT en una cookie HttpOnly (PyJWT). Límite de intentos en el inicio de sesión.
- **Seguridad:** validación de todas las entradas, CORS restringido, Content-Security-Policy y otras cabeceras, y protección contra fórmulas en el CSV exportado.
- **Frontend:** HTML, CSS y JavaScript sin frameworks ni librerías de gráficos. Gráficos propios en SVG y tipografía Geist con cifras tabulares.
- **Calidad:** pruebas con pytest y lint con ruff. El CI corre las pruebas con SQLite (Python 3.10 y 3.12) y con PostgreSQL 16.

## Estructura

```text
ExpenseFlow/
├── api/index.py              # Entrada para Vercel
├── backend/
│   ├── app.py                # Rutas de la API
│   ├── auth.py               # Registro, inicio de sesión y sesión
│   ├── database.py           # SQLite o PostgreSQL, esquema y datos de ejemplo
│   └── test_api.py           # Pruebas
├── frontend/
│   ├── index.html
│   ├── css/styles.css        # Colores, tipografía, claro y oscuro
│   └── js/
│       ├── api.js            # Cliente de la API
│       ├── app.js            # Pantallas, formularios, diálogos y avisos
│       ├── charts.js         # Gráficos en SVG
│       └── theme.js          # Tema claro u oscuro antes de pintar
├── docs/screenshots/         # Capturas del README
├── .github/workflows/ci.yml  # Lint y pruebas en cada push
├── ruff.toml, pytest.ini     # Configuración de ruff y pytest
├── requirements.txt          # Dependencias de la aplicación
├── requirements-dev.txt      # pytest y ruff
└── vercel.json
```

## Ejecutar en local

```bash
git clone https://github.com/KrlosEng/ExpenseFlow.git
cd ExpenseFlow
python -m venv venv
```

Activa el entorno (`.\venv\Scripts\Activate.ps1` en Windows, `source venv/bin/activate` en Linux o macOS) e instala las dependencias:

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

```bash
python -m uvicorn backend.app:app --reload --port 8000
```

Abre `http://127.0.0.1:8000` y crea una cuenta. Marca "Empezar con datos de ejemplo" para ver la aplicación con datos.

Sin variables de entorno se usa SQLite (`expenseflow.db`) y una clave de sesión temporal, así que la sesión se cierra cada vez que reinicias el servidor. Para evitarlo, define `SECRET_KEY`.

## Pruebas y lint

```bash
pytest -q
```

```bash
ruff check backend api
```

Las pruebas usan una base de datos temporal y nunca tocan `expenseflow.db`. Para correrlas contra PostgreSQL, define `TEST_DATABASE_URL` con una base desechable.

## Variables de entorno

| Variable | Obligatoria | Para qué sirve |
| :--- | :--- | :--- |
| `SECRET_KEY` | En producción | Firma las sesiones. Genera una con `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Sin ella la aplicación no arranca en Vercel. |
| `DATABASE_URL` | En producción | Conexión PostgreSQL (`postgresql://usuario:clave@host/db?sslmode=require`). Sin ella se usa SQLite. |
| `ALLOWED_ORIGINS` | No | Orígenes permitidos por CORS, separados por comas. Solo si el frontend está en otro dominio. |
| `COOKIE_SECURE` | No | `1` para enviar la cookie solo por HTTPS. Se activa sola en Vercel. |
| `DB_PATH` | No | Ruta del archivo SQLite. |
| `TEST_DATABASE_URL` | No | PostgreSQL desechable para correr las pruebas contra Postgres. |

## Desplegar en Vercel

1. Crea una base de datos PostgreSQL gratuita, por ejemplo en [Neon](https://neon.tech) o [Supabase](https://supabase.com), y copia su cadena de conexión.
2. Importa el repositorio en [Vercel](https://vercel.com).
3. En **Settings → Environment Variables** añade `DATABASE_URL` y `SECRET_KEY`.
4. Despliega. Las tablas se crean solas en el primer arranque.

Sin `DATABASE_URL`, Vercel usaría SQLite en `/tmp`, que se borra en cada arranque en frío, y los datos se perderían.

## API

Salvo `/api/health`, `/api/categories` y las rutas de `/api/auth`, todas requieren sesión y solo devuelven datos del usuario. Los errores responden con un código (400, 401, 404, 409, 422 o 429) y un `detail` legible.

| Método | Ruta | Qué hace |
| :--- | :--- | :--- |
| `POST` | `/api/auth/register` | Crear cuenta (inicia sesión) |
| `POST` | `/api/auth/login` | Iniciar sesión |
| `POST` | `/api/auth/logout` | Cerrar sesión |
| `GET` | `/api/auth/me` | Usuario actual, con su moneda |
| `PUT` | `/api/auth/me` | Cambiar nombre o moneda (COP, USD, EUR, MXN) |
| `GET` | `/api/health` | Estado del servidor y motor de base de datos |
| `GET` | `/api/categories` | Categorías de gasto e ingreso |
| `GET` | `/api/summary` | Resumen del mes (`?month=AAAA-MM`) y salud financiera |
| `GET` | `/api/transactions` | Movimientos con filtros y páginas (`page`, `page_size`); devuelve `items`, `total` y totales |
| `POST` | `/api/transactions` | Registrar movimiento |
| `PUT` | `/api/transactions/{id}` | Editar movimiento |
| `DELETE` | `/api/transactions/{id}` | Eliminar movimiento |
| `GET` | `/api/budgets` | Presupuestos con el gasto del mes (`?month=AAAA-MM`) |
| `POST` | `/api/budgets` | Crear o cambiar un límite |
| `GET` | `/api/savings_goals` | Metas de ahorro |
| `POST` | `/api/savings_goals` | Crear meta |
| `PUT` | `/api/savings_goals/{id}` | Editar meta (nombre, objetivo, fecha, categoría) |
| `PUT` | `/api/savings_goals/{id}/deposit` | Abonar a una meta |
| `DELETE` | `/api/savings_goals/{id}` | Eliminar meta |
| `GET` | `/api/subscriptions` | Suscripciones (registra antes los cobros vencidos) |
| `POST` | `/api/subscriptions` | Añadir suscripción |
| `PUT` | `/api/subscriptions/{id}` | Editar suscripción |
| `PUT` | `/api/subscriptions/{id}/toggle` | Pausar o activar |
| `DELETE` | `/api/subscriptions/{id}` | Eliminar suscripción |
| `POST` | `/api/import/csv` | Importar CSV (hasta 1.000 filas) |
| `POST` | `/api/import/json` | Importar JSON (hasta 1.000 movimientos) |
| `GET` | `/api/export/csv` | Exportar movimientos a CSV |

## Licencia

MIT. Consulta [LICENSE](LICENSE).

Creado por [KrlosEng](https://github.com/KrlosEng).
