from flask import (
    Flask, 
    render_template, 
    request, 
    redirect, 
    url_for, 
    send_from_directory, 
    send_file, 
    abort, 
    flash, 
    session, 
    make_response
)
from flask_session import Session
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from werkzeug.utils import safe_join
from backup_config import backup_konfigurasi, perangkat_juniper, perangkat_hp_comware
import logging
import os
import zipfile
import datetime as dt
from io import BytesIO
from functools import wraps
import io
import sys
from flask_bcrypt import Bcrypt
from flask_mysqldb import MySQL
from flask_wtf.csrf import CSRFProtect
import pandas as pd
from config.dbconfig import MYSQL_CONFIG 
from flask_login import LoginManager, login_user, login_required, logout_user, UserMixin
from datetime import timedelta

FolderPath = r'hasil-backup'


app = Flask(__name__, template_folder='templates')
app.config['SECRET_KEY'] = 'KvBRVpO3ltFH0WLTaO38WA'
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
app.config["SESSION_FILE_DIR"] = "flask_session"
# Konfigurasi MySQL
app.config.update(MYSQL_CONFIG)

mysql = MySQL(app)
bcrypt = Bcrypt(app)
csrf = CSRFProtect(app)

Session(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Anda harus login untuk mengakses halaman ini."
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"
login_manager.remember_cookie_duration = timedelta(minutes=5)

app.permanent_session_lifetime = timedelta(minutes=5)

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    return User(user_id)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_input = request.form['password']
        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()
        cursor.close()
        if user and bcrypt.check_password_hash(user['password'], password_input):
            user_obj = User(user['id'])
            login_user(user_obj)
            session['username'] = user['username']
            flash('Login Berhasil', 'success')
            return redirect(url_for('base'))
        else:
            flash('Login Gagal. Periksa kembali username dan password Anda.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('username', None)
    flash('Logout berhasil.', 'success')
    return redirect(url_for('login'))

@app.route('/home')
@login_required
def base():
    if 'username' in session:
        username = session['username']
        return render_template('base.html', username=username)  # Pastikan Anda memiliki file base.html di dalam folder templates
    return redirect(url_for('login'))

@app.route('/')
def home():
    if 'username' in session:
        username = session['username']
        return render_template('base.html', username=username)
    return 'Anda belum login! <a href="/login">Login di sini</a>'

def getReadableByteSize(num, suffix='B') -> str:
    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(num) < 1024.0:
            return "%3.1f%s%s" % (num, unit, suffix)
        num /= 1024.0
    return "%.1f%s%s" % (num, 'Y', suffix)

def getTimeStampString(tSec: float) -> str:
    tObj = dt.datetime.fromtimestamp(tSec)
    tStr = dt.datetime.strftime(tObj, '%Y-%m-%d %H:%M:%S')
    return tStr

def getIconClassForFilename(fName):
    fileExt = Path(fName).suffix
    fileExt = fileExt[1:] if fileExt.startswith(".") else fileExt
    fileTypes = ["aac", "ai", "bmp", "cs", "css", "csv", "doc", "docx", "exe", "gif", "heic", "html", "java", "jpg", "js", "json", "jsx", "key", "m4p", "md", "mdx", "mov", "mp3",
                 "mp4", "otf", "pdf", "php", "png", "pptx", "psd", "py", "raw", "rb", "sass", "scss", "sh", "sql", "svg", "tiff", "tsx", "ttf", "txt", "wav", "woff", "xlsx", "xml", "yml"]
    fileIconClass = f"bi bi-filetype-{fileExt}" if fileExt in fileTypes else "bi bi-file-earmark"
    return fileIconClass

# route handler
@app.route('/reports/', defaults={'reqPath': ''})
@app.route('/reports/<path:reqPath>')
@login_required
def getFiles(reqPath):
    
    # Join the base and the requested path
    # could have done os.path.join, but safe_join ensures that files are not fetched from parent folders of the base folder
    absPath = safe_join(FolderPath, reqPath)

    # Return 404 if path doesn't exist
    if not os.path.exists(absPath):
        return abort(404)

    # Check if path is a file and serve
    if os.path.isfile(absPath):
        return send_file(absPath)

    # Show directory contents
    def fObjFromScan(x):
        fileStat = x.stat()
        # return file information for rendering
        return {'name': x.name,
                'fIcon': "bi bi-folder-fill" if os.path.isdir(x.path) else getIconClassForFilename(x.name),
                'relPath': os.path.relpath(x.path, FolderPath).replace("\\", "/"),
                'mTime': getTimeStampString(fileStat.st_mtime),
                'size': getReadableByteSize(fileStat.st_size),
                'isDir': os.path.isdir(x.path)}  # Added 'isDir' to indicate if the object is a directory
    fileObjs = [fObjFromScan(x) for x in os.scandir(absPath)]
    # get parent directory url
    parentFolderPath = os.path.relpath(
        Path(absPath).parents[0], FolderPath).replace("\\", "/")
    if 'username' in session:
        username = session['username']
        return render_template('daftar.html', data={'files': fileObjs,
                                                 'parentFolder': parentFolderPath}, username=username)  # Pastikan Anda memiliki file base.html di dalam folder templates
    return redirect(url_for('login'))
    # return render_template('daftar.html', data={'files': fileObjs,
    #                                              'parentFolder': parentFolderPath})
def reports():
    if 'username' in session:
        username = session['username']
        return render_template('base.html', username=username)  # Pastikan Anda memiliki file base.html di dalam folder templates
    return redirect(url_for('login'))
@app.route('/backup-config')
@login_required
def backup_config():
    if 'username' in session:
        username = session['username']
        return render_template('backup_config.html', username=username)  # Pastikan Anda memiliki file base.html di dalam folder templates
    return redirect(url_for('login'))
    # return render_template('backup_config.html')

@app.route('/download-zip', methods=['GET','POST'])
@login_required
def download_zip():
    reqPath = request.args.get('reqPath', '')  # Mendapatkan reqPath dari parameter query
    zip_name = f'{reqPath}.zip'
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(os.path.join(FolderPath, reqPath)):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, os.path.join(FolderPath, reqPath)))

    zip_buffer.seek(0)
    return send_file(zip_buffer, as_attachment=True, download_name=zip_name, mimetype='application/zip')
def create_zip_from_directory(directory_path, zip_name):
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                zip_file.write(file_path, os.path.relpath(file_path, directory_path))
    zip_buffer.seek(0)
    return zip_buffer

@app.route('/download-reports-zip')
@login_required
def download_reports_zip():
    zip_name = 'all.zip'
    # Membuat ZIP dari seluruh direktori laporan
    zip_buffer = create_zip_from_directory(FolderPath, zip_name)
    
    # Mengirim file ZIP sebagai respons
    return send_file(zip_buffer, as_attachment=True, download_name=zip_name, mimetype='application/zip')

@app.route('/trigger-backup')
@login_required
def trigger_backup():
    # Menyimpan referensi ke stdout asli
    original_stdout = sys.stdout
    
    # Membuat objek StringIO untuk menangkap output
    captured_output = io.StringIO()
    sys.stdout = captured_output

    try:
        logging.info('Backup dimulai pada: %s', dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_juniper = executor.submit(backup_konfigurasi, perangkat_juniper)
            future_hp_comware = executor.submit(backup_konfigurasi, perangkat_hp_comware)
            result_juniper = future_juniper.result(timeout=360)  # Timeout 360 detik
            result_hp_comware = future_hp_comware.result(timeout=360)
            flash('Backup berhasil disimpan.', 'success')
    except TimeoutError:
        flash('Proses backup melebihi batas waktu', 'warning')
    except Exception as e:
        flash(f'Terjadi kesalahan: {str(e)}', 'danger')

    # Mengembalikan stdout ke aslinya
    sys.stdout = original_stdout
    
    # Mendapatkan isi output yang ditangkap
    output = captured_output.getvalue()
    
    # Menutup objek StringIO
    captured_output.close()

    if 'username' in session:
        username = session['username']
        # Mengirim output yang ditangkap ke template untuk ditampilkan
        return render_template('backup_config.html', username=username, output=output)
    return redirect(url_for('login'))

@app.route('/info')
@login_required
def info():
    if 'username' in session:
        username = session['username']
        return render_template('info.html', username=username)  # Pastikan Anda memiliki file base.html di dalam folder templates
    return redirect(url_for('login'))

@app.route('/view-device')
@login_required
def view_perangkat():
    page = request.args.get('page', 1, type=int)
    perpage = 5
    startat = (page - 1) * perpage
    search_query = request.args.get('search', '')  # Mendapatkan query pencarian dari parameter URL

    cursor = mysql.connection.cursor()

    # Modifikasi query untuk menambahkan pencarian berdasarkan nama, hostname, atau IP
    if search_query:
        search_like = f"%{search_query}%"
        cursor.execute('SELECT * FROM perangkat WHERE nama LIKE %s OR hostname LIKE %s OR ip LIKE %s LIMIT %s, %s;', (search_like, search_like, search_like, startat, perpage))
    else:
        cursor.execute('SELECT * FROM perangkat LIMIT %s, %s;', (startat, perpage))

    data = list(cursor.fetchall())

    # Mengubah nama perangkat
    data_perangkat = []
    for perangkat in data:
        if 'ip_perangkat_juniper' in perangkat['nama']:
            nama = 'JUNIPER'
        elif 'ip_perangkat_h3c' in perangkat['nama']:
            nama = 'H3C'
        else:
            nama = perangkat['nama']  # Jika tidak cocok, gunakan nama asli

        # Menyalin objek perangkat dan mengupdate nama
        perangkat_modifikasi = dict(perangkat)
        perangkat_modifikasi['nama'] = nama
        data_perangkat.append(perangkat_modifikasi)

    # Menghitung total halaman dengan atau tanpa pencarian
    if search_query:
        cursor.execute('SELECT COUNT(*) FROM perangkat WHERE nama LIKE %s OR hostname LIKE %s OR ip LIKE %s', (search_like, search_like, search_like))
    else:
        cursor.execute('SELECT COUNT(*) FROM perangkat')
    total = cursor.fetchone()
    total_pages = total['COUNT(*)'] // perpage + (total['COUNT(*)'] % perpage > 0)

    # Logika pagination
    left_window = max(1, page - 2)
    right_window = min(total_pages, page + 2)
    
    cursor.close()

    if 'username' in session:
        username = session['username']
        return render_template('view_device.html', perangkat=data_perangkat, username=username, page=page, total_pages=total_pages, left_window=left_window, right_window=right_window, search_query=search_query)
    return redirect(url_for('login'))

@app.route('/upload-excel', methods=['POST'])
@login_required
def upload_excel():
    if 'file' not in request.files:
        flash('Tidak ada file bagian', 'danger')
        return redirect(request.url)
    file = request.files['file']
    if file.filename == '':
        flash('Tidak ada file yang dipilih', 'danger')
        return redirect(request.url)
    if file and file.filename.endswith('.xlsx'):
        try:
            df = pd.read_excel(file)
            cursor = mysql.connection.cursor()
            for index, row in df.iterrows():
                cursor.execute("INSERT INTO perangkat (nama, hostname, ip, location, username, password) VALUES (%s, %s, %s, %s, %s, %s)", 
                               (row['nama'], row['hostname'], row['ip'], row['location'], row['username'], row['password']))
            mysql.connection.commit()
            cursor.close()
            flash('Data berhasil diimport dari Excel.', 'success')
        except Exception as e:
            flash(f'Error: {str(e)}', 'danger')
    else:
        flash('Format file tidak didukung', 'danger')
    return redirect(url_for('view_perangkat'))

@app.route('/export-excel')
@login_required
def export_excel():
    cursor = mysql.connection.cursor()
    query = "SELECT * FROM perangkat"
    cursor.execute(query)
    result = cursor.fetchall()
    cursor.close()

    # Konversi hasil query ke DataFrame pandas
    df = pd.DataFrame(result)

    # Tentukan nama file Excel yang akan dihasilkan
    excel_file = BytesIO()
    with pd.ExcelWriter(excel_file, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Perangkat', index=False)

    excel_file.seek(0)

    # Membuat response
    response = make_response(excel_file.getvalue())
    response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    response.headers['Content-Disposition'] = 'attachment; filename=Daftar_Perangkat.xlsx'

    return response

@app.route('/hapus-perangkat/<int:id>', methods=['GET'])
@login_required
def hapus_perangkat(id):
    try:
        cursor = mysql.connection.cursor()
        cursor.execute("DELETE FROM perangkat WHERE id = %s", (id,))
        mysql.connection.commit()
        cursor.close()
        flash('Perangkat berhasil dihapus', 'success')
    except Exception as e:
        flash('Gagal menghapus perangkat: ' + str(e), 'danger')
    return redirect(url_for('view_perangkat'))

@app.route('/edit-perangkat/<int:id>', methods=['GET'])
@login_required
def edit_perangkat(id):
    cursor = mysql.connection.cursor()
    cursor.execute("SELECT * FROM perangkat WHERE id = %s", (id,))
    perangkat = cursor.fetchone()
    cursor.close()

    if 'ip_perangkat_juniper' in perangkat['nama']:
        perangkat['nama'] = 'ip_perangkat_juniper'
    elif 'ip_perangkat_h3c' in perangkat['nama']:
        perangkat['nama'] = 'ip_perangkat_h3c'

    if 'username' in session:
        username = session['username']
        return render_template('edit_perangkat.html', perangkat=perangkat, username=username)
    return redirect(url_for('login'))

@app.route('/update-perangkat', methods=['POST'])
@login_required
def update_perangkat():
    id = request.form['id']
    base_nama = request.form['nama']
    hostname = request.form['hostname']
    location = request.form['location']
    ip = request.form['ip']
    username = request.form['username']  # Menambahkan input username
    password = request.form['password']  # Menambahkan input password
    
    # Menghitung jumlah entri untuk jenis perangkat yang dipilih
    cursor = mysql.connection.cursor()
    query = "SELECT COUNT(*) FROM perangkat WHERE nama LIKE %s"
    like_pattern = f"{base_nama}%"
    cursor.execute(query, (like_pattern,))
    result = cursor.fetchone()

    if result is None:
        jumlah = 0
    else:
        jumlah = result['COUNT(*)']

    nama = f"{base_nama}_{jumlah + 1}"
    
    # Memperbarui data di database termasuk username dan password
    cursor.execute("UPDATE perangkat SET nama=%s, ip=%s, location=%s, hostname=%s, username=%s, password=%s WHERE id=%s", (nama, ip, location, hostname, username, password, id))
    mysql.connection.commit()
    cursor.close()
    flash('Perangkat berhasil diupdate.', 'success')
    return redirect(url_for('view_perangkat'))

@app.route('/tambah-perangkat', methods=['GET'])
@login_required
def form_tambah_perangkat():
    if 'username' in session:
        username = session['username']
        return render_template('add_device.html', username=username)
    return redirect(url_for('login'))

@app.route('/tambah-perangkat', methods=['POST'])
@login_required
def tambah_perangkat():
    base_nama = request.form['nama']
    hostname = request.form['hostname']
    location = request.form['location']
    ip = request.form['ip']
    username = request.form['username']  # Menambahkan input username
    password = request.form['password']  # Menambahkan input password
    
    # Menghitung jumlah entri untuk jenis perangkat yang dipilih
    cursor = mysql.connection.cursor()
    query = "SELECT COUNT(*) FROM perangkat WHERE nama LIKE %s"
    like_pattern = f"{base_nama}%"
    cursor.execute(query, (like_pattern,))
    result = cursor.fetchone()

    if result is None:
        jumlah = 0
    else:
        jumlah = result['COUNT(*)']

    nama = f"{base_nama}_{jumlah + 1}"
    
    # Menambahkan data ke database termasuk username dan password
    cursor.execute("INSERT INTO perangkat (nama, hostname, ip, location, username, password) VALUES (%s, %s, %s, %s, %s, %s)", (nama, hostname, ip, location, username, password))
    mysql.connection.commit()
    cursor.close()
    flash('Perangkat berhasil ditambahkan.', 'success')
    return redirect(url_for('view_perangkat'))

@app.route('/edit-password', methods=['GET', 'POST'])
@login_required
def edit_password():
    if request.method == 'POST':
        old_password = request.form['old_password']
        new_password = request.form['new_password']
        username = session['username']

        cursor = mysql.connection.cursor()
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cursor.fetchone()

        if user and bcrypt.check_password_hash(user['password'], old_password):
            new_password_hash = bcrypt.generate_password_hash(new_password).decode('utf-8')
            cursor.execute('UPDATE users SET password = %s WHERE username = %s', (new_password_hash, username))
            mysql.connection.commit()
            flash('Password berhasil diperbarui.', 'success')
            return redirect(url_for('base'))
        else:
            flash('Password lama salah.', 'danger')

    return render_template('edit_password.html')

if __name__ == '__main__':
    app.run(debug=True)
