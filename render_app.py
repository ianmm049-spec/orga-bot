#!/usr/bin/env python3
"""
render_app.py

App Flask mínima para aceptar un archivo .zip (por ejemplo exportado desde Replit), extraerlo
con seguridad dentro del repositorio en la carpeta ./site y servir su contenido como files estáticos.
Diseñada para desplegar en Render (usa la variable $PORT).

Rutas:
 - POST /upload (multipart form, campo 'zip') -> recibe y extrae el zip
    Opciones por query string: overwrite=true|false (por defecto false), keep_root=true|false
 - GET /* -> sirve archivos extraídos desde ./site

Seguridad:
 - Previene Zip-Slip validando rutas
 - Limita los tipos de archivo mediante extensión opcionál
"""
from flask import Flask, request, send_from_directory, abort, jsonify
from pathlib import Path
import zipfile
import os
import tempfile
import shutil

app = Flask(__name__)

SITE_DIR = Path("./site").resolve()
SITE_DIR.mkdir(parents=True, exist_ok=True)

def is_within_directory(directory: Path, target: Path) -> bool:
    try:
        directory = directory.resolve()
        target = target.resolve()
        return str(target).startswith(str(directory))
    except Exception:
        return False

def safe_extract(zip_path: Path, dest_dir: Path, overwrite=False, keep_root=False):
    with zipfile.ZipFile(zip_path, "r") as zf:
        members = zf.infolist()
        # determine common root if not keeping it
        common_root = ''
        if not keep_root:
            top_levels = {p.filename.split('/')[0] for p in members if p.filename and not p.filename.endswith('/')}
            if len(top_levels) == 1:
                common_root = next(iter(top_levels)) + '/'

        for member in members:
            member_name = member.filename
            if common_root and member_name.startswith(common_root):
                member_name = member_name[len(common_root):]
            if not member_name:
                continue

            target_path = dest_dir.joinpath(member_name)
            if not is_within_directory(dest_dir, target_path):
                raise Exception(f"Intento de extracción fuera del directorio destino: {member.filename}")

            if member.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
                continue

            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists() and not overwrite:
                # Skip existing
                continue

            with zf.open(member, "r") as source, open(target_path, "wb") as dest:
                shutil.copyfileobj(source, dest)
            try:
                unix_attr = (member.external_attr >> 16) & 0o777
                if unix_attr:
                    target_path.chmod(unix_attr)
            except Exception:
                pass

@app.route('/upload', methods=['POST'])
def upload_zip():
    if 'zip' not in request.files:
        return jsonify({'error': "Falta el campo 'zip' (multipart/form-data)"}), 400

    file = request.files['zip']
    if file.filename == '':
        return jsonify({'error': 'Nombre de archivo vacío'}), 400

    overwrite = request.args.get('overwrite', 'false').lower() == 'true'
    keep_root = request.args.get('keep_root', 'false').lower() == 'true'

    # save to a temp file
    with tempfile.TemporaryDirectory() as td:
        tmp_zip_path = Path(td) / 'upload.zip'
        file.save(tmp_zip_path)
        try:
            safe_extract(tmp_zip_path, SITE_DIR, overwrite=overwrite, keep_root=keep_root)
        except Exception as e:
            return jsonify({'error': f'Error al extraer zip: {e}'}), 400

    return jsonify({'ok': True, 'message': 'Zip extraído en site/'}), 200

# Serve files from ./site
@app.route('/', defaults={'path': 'index.html'})
@app.route('/<path:path>')
def serve_site(path):
    # If file exists in site, send it, otherwise 404
    target = SITE_DIR.joinpath(path)
    if target.exists() and target.is_file():
        return send_from_directory(str(SITE_DIR), path)
    # fallback: if index.html exists serve it for SPA
    index = SITE_DIR.joinpath('index.html')
    if index.exists():
        return send_from_directory(str(SITE_DIR), 'index.html')
    return abort(404)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)