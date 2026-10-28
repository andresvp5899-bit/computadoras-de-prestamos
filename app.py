import os, json, time, threading, logging, csv, io
from datetime import datetime, timezone
from pathlib import Path
import gspread
from flask import Flask, render_template, jsonify, request, Response
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv

load_dotenv()
app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
LOCK = threading.RLock()
CACHE = {'until': 0, 'data': None}
HEADERS = ['ITEM', 'DEPARTAMENTO', 'UBICACION ACTUAL', 'OBSERVACION', 'ESTADO']
HISTORY = ['FECHA UTC', 'ITEM', 'ACCION', 'DEPARTAMENTO', 'UBICACION', 'ESTADO', 'OBSERVACION']
STATES = {'Disponible', 'Prestado', 'Mantenimiento'}

def book():
    raw = os.getenv('GOOGLE_CREDENTIALS_JSON', '').strip()
    if raw:
        data = json.loads(raw)
    else:
        path = Path(os.getenv('GOOGLE_CREDENTIALS_FILE', 'credenciales.json'))
        if not path.is_absolute(): path = Path(__file__).resolve().parent / path
        if not path.is_file(): raise RuntimeError('Faltan credenciales: configurá GOOGLE_CREDENTIALS_JSON o GOOGLE_CREDENTIALS_FILE.')
        data = json.loads(path.read_text(encoding='utf-8'))
    creds = Credentials.from_service_account_info(data, scopes=['https://www.googleapis.com/auth/spreadsheets'])
    sid = os.getenv('GOOGLE_SHEET_ID', '').strip()
    if not sid: raise RuntimeError('Falta GOOGLE_SHEET_ID en .env')
    return gspread.authorize(creds).open_by_key(sid)

def sheet(b):
    name = os.getenv('GOOGLE_WORKSHEET', 'PRESTAMO').strip() or 'PRESTAMO'
    ws = b.worksheet(name)
    current = ws.row_values(1)
    if not any(current):
        ws.update(range_name='A1:E1', values=[HEADERS])
    elif len(current) < 4 or [x.strip().upper() for x in current[:4]] != HEADERS[:4]:
        raise RuntimeError('Encabezados A-D distintos a ITEM, DEPARTAMENTO, UBICACION ACTUAL, OBSERVACION')
    elif len(current) < 5 or current[4].strip().upper() != 'ESTADO':
        if len(current) >= 5 and current[4].strip(): raise RuntimeError('Columna E ocupada; se necesita ESTADO')
        ws.update(range_name='E1', values=[['ESTADO']])
    return ws

def rows(ws, force=False):
    if not force and CACHE['data'] is not None and time.monotonic() < CACHE['until']:
        return [dict(x) for x in CACHE['data']]
    values = ws.get('A2:E')
    out=[]
    for i, r in enumerate(values, 2):
        r=(r+['']*5)[:5]
        if not r[0].strip(): continue
        out.append({'item':r[0], 'departamento':r[1], 'ubicacion':r[2], 'observacion':r[3], 'estado':r[4] if r[4] in STATES else 'Prestado', '_row':i})
    CACHE.update(until=time.monotonic()+6, data=out)
    return [dict(x) for x in out]

def clear_cache(): CACHE.update(until=0, data=None)

def next_item(ws, current):
    meta=ws.acell('H2').value or '0'
    maximum=max((int(x['item']) for x in current if x['item'].isdigit()), default=0)
    number=max(int(meta) if meta.isdigit() else 0, maximum)+1
    ws.update(range_name='H1:H2', values=[['ULTIMO_ITEM'],[str(number)]])
    return number

def payload():
    d=request.get_json(silent=True) or {}
    v={k:str(d.get(k,'')).strip()[:limit] for k,limit in [('departamento',120),('ubicacion',120),('observacion',500),('estado',30)]}
    if not v['departamento'] or not v['ubicacion']: raise ValueError('Departamento y ubicación son obligatorios.')
    if v['estado'] not in STATES: raise ValueError('Estado inválido.')
    return v

def history(b, item, action, v):
    try: ws=b.worksheet('HISTORIAL')
    except gspread.WorksheetNotFound:
        ws=b.add_worksheet(title='HISTORIAL',rows=2000,cols=8)
        ws.update(range_name='A1:G1',values=[HISTORY])
    ws.append_row([datetime.now(timezone.utc).isoformat(),str(item),action,v.get('departamento',''),v.get('ubicacion',''),v.get('estado',''),v.get('observacion','')],value_input_option='RAW')

@app.get('/')
def home():
    images=sorted(p.name for p in (Path(app.static_folder)/'img').iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png','.webp'})
    return render_template('index.html', images=images)

@app.get('/api/equipos')
def list_equipment():
    try:
        with LOCK: data=rows(sheet(book()))
        for x in data: x.pop('_row',None)
        return jsonify(ok=True,equipos=data)
    except Exception as exc:
        app.logger.exception('Error al consultar Google Sheets')
        return jsonify(ok=False,mensaje='No se pudo consultar Google Sheets. Revisá .env, credenciales, permisos y el nombre PRESTAMO.'),503

@app.post('/api/equipos')
def create():
    try: v=payload()
    except ValueError as exc: return jsonify(ok=False,mensaje=str(exc)),400
    try:
        with LOCK:
            b=book(); ws=sheet(b); current=rows(ws,True); number=next_item(ws,current)
            ws.append_row([number,v['departamento'],v['ubicacion'],v['observacion'],v['estado']],value_input_option='RAW',table_range='A:E')
            clear_cache()
            try: history(b,number,'REGISTRO',v)
            except Exception: app.logger.exception('No se pudo registrar historial')
        return jsonify(ok=True,item=number),201
    except Exception:
        app.logger.exception('Error al crear'); return jsonify(ok=False,mensaje='No se pudo guardar. Revisá el registro del servidor.'),503

@app.put('/api/equipos/<int:item>')
def update(item):
    try: v=payload()
    except ValueError as exc: return jsonify(ok=False,mensaje=str(exc)),400
    try:
        with LOCK:
            b=book(); ws=sheet(b); found=next((x for x in rows(ws,True) if x['item']==str(item)),None)
            if not found: return jsonify(ok=False,mensaje='Ítem no encontrado'),404
            ws.update(range_name=f'B{found["_row"]}:E{found["_row"]}',values=[[v['departamento'],v['ubicacion'],v['observacion'],v['estado']]])
            clear_cache()
            try: history(b,item,'DEVOLUCION' if v['estado']=='Disponible' and found['estado']!='Disponible' else 'EDICION',v)
            except Exception: app.logger.exception('No se pudo registrar historial')
        return jsonify(ok=True)
    except Exception:
        app.logger.exception('Error al editar'); return jsonify(ok=False,mensaje='No se pudo actualizar.'),503

@app.delete('/api/equipos/<int:item>')
def delete(item):
    try:
        with LOCK:
            b=book(); ws=sheet(b); found=next((x for x in rows(ws,True) if x['item']==str(item)),None)
            if not found: return jsonify(ok=False,mensaje='Ítem no encontrado'),404
            try: history(b,item,'ELIMINACION',found)
            except Exception: app.logger.exception('No se pudo registrar historial')
            ws.delete_rows(found['_row']);clear_cache()
        return jsonify(ok=True)
    except Exception:
        app.logger.exception('Error al eliminar');return jsonify(ok=False,mensaje='No se pudo eliminar.'),503

@app.get('/api/historial')
def get_history():
    try:
        with LOCK:
            b=book()
            try: ws=b.worksheet('HISTORIAL')
            except gspread.WorksheetNotFound: return jsonify(ok=True,historial=[])
            values=ws.get('A2:G')
        data=[dict(zip(['fecha','item','accion','departamento','ubicacion','estado','observacion'],(r+['']*7)[:7])) for r in values]
        return jsonify(ok=True,historial=data[::-1][:500])
    except Exception:
        app.logger.exception('Error historial');return jsonify(ok=False,mensaje='No se pudo cargar historial.'),503

@app.get('/health')
def health(): return jsonify(ok=True)

if __name__=='__main__': app.run(host='0.0.0.0',port=int(os.getenv('PORT','5000')))
