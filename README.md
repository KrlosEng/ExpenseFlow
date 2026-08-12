# 💎 ExpenseFlow — FinTech & Expense Management App

**ExpenseFlow** (anteriormente AuraFinance Engine) es una plataforma web moderna e interactiva para la gestión de finanzas personales, seguimiento de gastos, ingresos, suscripciones recurrentes y métricas de salud financiera con inteligencia algorítmica.

![License](https://img.shields.io/badge/License-MIT-blue.svg)
![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white)
![Vercel](https://img.shields.io/badge/Vercel-Deployed-000000?logo=vercel&logoColor=white)

---

## ✨ Características Principales

- 📊 **Financial Health Score**: Algoritmo dinámico que calcula tu puntuación de salud financiera (0 a 100 pts) y genera recomendaciones personalizadas según tus hábitos de ahorro y gasto.
- 💸 **Gestión de Transacciones**: Registro, filtrado y búsqueda en tiempo real de ingresos y gastos categorizados.
- 🔄 **Control de Suscripciones**: Monitoreo de servicios recurrentes (Netflix, Spotify, Cloud, etc.) con cálculo automático del impacto mensual.
- 🎯 **Metas de Ahorro**: Define metas financieras con barra de progreso interactiva e historial de depósitos.
- 📈 **Presupuestos & Gráficos**: Gráficos interactivos de distribución por categoría y tendencia diaria de gastos.
- ⚡ **Deploy Listo para Vercel**: Estructura lista para desplegar en Vercel con Backend Serverless en Python.

---

## 🛠️ Tecnologías Utilizadas

### **Backend**
- **Python 3.10+**
- **FastAPI**: Framework web asíncrono de alto rendimiento.
- **SQLite**: Base de datos ligera embebida (adaptada a `/tmp` en serverless).
- **Pydantic**: Validación de datos y modelos REST.

### **Frontend**
- **HTML5 & Vanilla CSS**: Interfaz moderna con modo oscuro y diseño responsive glassmorphism.
- **JavaScript (ES6 Modules)**: Lógica frontend sin dependencias pesadas.
- **FontAwesome & Google Fonts**: Iconografía y tipografía premium.

---

## 📁 Estructura del Proyecto

```text
expenseflow/
├── api/
│   └── index.py            # Entrypoint Serverless para Vercel (@vercel/python)
├── backend/
│   ├── app.py              # Aplicación principal FastAPI y rutas API REST
│   ├── database.py         # Conexión SQLite y creación de tablas
│   └── test_api.py         # Pruebas unitarias de API
├── frontend/
│   ├── index.html          # Dashboard principal
│   ├── css/
│   │   └── styles.css      # Estilos CSS con diseño dark mode premium
│   └── js/
│       ├── api.js          # Cliente HTTP API
│       ├── app.js          # Controladores y UI
│       └── charts.js       # Gráficos y renderizado de métricas
├── expenseflow.db          # Base de datos SQLite local
├── requirements.txt        # Dependencias de Python
└── vercel.json             # Configuración de rutas y builds para Vercel
```

---

## 🚀 Instalación y Ejecución Local

### 1. Clonar el repositorio
```bash
git clone https://github.com/KrlosEng/ExpenseFlow.git
cd ExpenseFlow
```

### 2. Crear y activar un entorno virtual (opcional pero recomendado)
```bash
python -m venv venv
# En Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# En Linux/macOS:
source venv/bin/activate
```

### 3. Instalar dependencias
```bash
pip install -r requirements.txt
```

### 4. Iniciar el servidor backend local
```bash
python -m uvicorn backend.app:app --reload --port 8000
```
El backend estará disponible en `http://127.0.0.1:8000`.

### 5. Abrir el Frontend
Abre el archivo `frontend/index.html` en tu navegador o sírvelo con una extensión de Live Server.

---

## ☁️ Despliegue en Vercel

Este proyecto ya incluye la configuración `vercel.json` y el punto de entrada `api/index.py` listos para Vercel.

1. Conecta tu repositorio de GitHub a [Vercel](https://vercel.com).
2. Crea un nuevo proyecto seleccionando el repositorio **ExpenseFlow**.
3. Haz clic en **Deploy**. Vercel compilará automáticamente las Serverless Functions de FastAPI y los archivos estáticos del frontend.

---

## 🛰️ Rutas Principales de la API REST

| Método | Endpoint | Descripción |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Estado del servidor API |
| `GET` | `/api/summary` | Resumen general, Health Score y métricas |
| `GET` | `/api/transactions` | Listar y filtrar transacciones |
| `POST` | `/api/transactions` | Crear nueva transacción |
| `DELETE` | `/api/transactions/{id}` | Eliminar transacción |
| `GET` | `/api/subscriptions` | Obtener lista de suscripciones |
| `POST` | `/api/subscriptions` | Agregar suscripción |
| `GET` | `/api/savings_goals` | Obtener metas de ahorro |
| `POST` | `/api/savings_goals` | Crear nueva meta de ahorro |
| `PUT` | `/api/savings_goals/{id}/deposit` | Realizar depósito a una meta |

---

## 📄 Licencia

Este proyecto se distribuye bajo la licencia MIT. Consulta `LICENSE` para más información.

Creado por [KrlosEng](https://github.com/KrlosEng).
