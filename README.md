# Picksy

Aplicación web que permite buscar un producto con un presupuesto máximo y compara precios de varias tiendas colombianas. Guarda usuarios y su historial de búsquedas.

## Tecnologías
- Backend: Python + FastAPI (puerto 8000)
- Frontend: HTML, CSS y JavaScript (puerto 5500)
- Base de datos: PostgreSQL (Picksy)

## Cómo ejecutar
### Backend
cd Picksy_Backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   (y completar tus datos)
uvicorn main:app --reload --port 8000

### Frontend
Abrir Picksy_Frontend/Picksy_Frontend/Picksy/index.html con Live Server (puerto 5500).

## Documentación
- ERS: SmartBudget_ERS_Ingenieria_de_Requerimientos.docx
- Presentación: SmartBudget_presentacion.pptx.pdf
