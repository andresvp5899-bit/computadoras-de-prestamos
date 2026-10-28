# COMPUTADORAS DE PRÉSTAMOS — ANIME EDITION 2.0

## Configuración local

1. Instalar Python 3.11+.
2. En esta carpeta ejecutar `pip install -r requirements.txt`.
3. Copiar `.env.example` a `.env`.
4. Colocar `credenciales.json` de la cuenta de servicio en esta carpeta (NO subirlo a GitHub).
5. Compartir la hoja Google Sheets con el correo `client_email` del JSON como **Editor**.
6. Verificar que el ID y el nombre `PRESTAMO` en `.env` sean correctos.
7. Ejecutar `python app.py` y abrir `http://127.0.0.1:5000`.

## Google Sheets

Se usan las columnas originales A-D: `ITEM`, `DEPARTAMENTO`, `UBICACION ACTUAL`, `OBSERVACION`. Se añade **E: ESTADO** sin borrar las anteriores. Las filas anteriores sin estado se interpretan como **Prestado** hasta editarlas. La celda **H2** guarda el último ítem asignado. Se crea otra pestaña `HISTORIAL` para registrar cambios; las operaciones del historial se intentan registrar, pero si falla la pestaña el movimiento principal puede quedar guardado sin historial. **Hacé una copia de la hoja antes de probar.**

## Seguridad y despliegue

Este sistema se entrega sin login, como solicitaste. No lo publiques sin restringir el acceso a usuarios de confianza: cualquier visitante puede modificar o borrar registros. `credenciales.json` y `.env` están en `.gitignore`; verificá que no estén ya versionados antes de hacer push. Para Render se puede definir `GOOGLE_CREDENTIALS_JSON` con el JSON completo y `GOOGLE_SHEET_ID`, `GOOGLE_WORKSHEET=PRESTAMO` como variables privadas.

## Funciones

- Fondos anime completos, imagen central sin recorte, fondo lateral difuminado y rotación cada 5 segundos.
- Control de intensidad, modo solo imagen y navegación manual.
- Altas, edición, devolución, eliminación, estados, filtros, paginación, CSV e historial.
- Impresión Honeywell 70 × 28 mm (ítem y departamento).

La exportación CSV puede abrirse en Excel. No se garantiza conexión con Google Sheets hasta configurar credenciales y permisos.
