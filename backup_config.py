from netmiko import ConnectHandler
from datetime import datetime
import os
import shutil
import mysql.connector


# Fungsi untuk membuat direktori jika belum ada
def buat_direktori(path):
    if not os.path.exists(path):
        os.makedirs(path)
        # os.chmod(path, 0o777)

# Membuat direktori hasil-backup jika belum ada
backup_dir = 'hasil-backup'
buat_direktori(backup_dir)

def daftar_file_dan_direktori():
    direktori = 'hasil-backup'  # Sesuaikan dengan lokasi direktori output Anda
    daftar = []
    try:
        for item in os.listdir(direktori):
            full_path = os.path.join(direktori, item)
            if os.path.isfile(full_path):
                daftar.append(('file', item))
            elif os.path.isdir(full_path):
                daftar.append(('dir', item))
        return daftar
    except FileNotFoundError:
        return []

# Fungsi untuk mengambil kredensial dari database MySQL
def ambil_kredensial_dari_db():
    try:
        # Menghubungkan ke database
        conn = mysql.connector.connect(
            host="localhost",  # atau alamat IP server MySQL Anda
            user="root",  # ganti dengan username database Anda
            password="",  # ganti dengan password database Anda
            database="h2py"  # ganti dengan nama database Anda
        )
        cursor = conn.cursor()
        # Sesuaikan query untuk mengambil nama, ip, username, dan password
        cursor.execute("SELECT nama, ip, username, password FROM perangkat")  
        kredensial_dict = {nama: {'ip': ip, 'username': username, 'password': password} for nama, ip, username, password in cursor}
        cursor.close()
        conn.close()
        return kredensial_dict
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return {}

# Mengganti bagian ini dengan fungsi ambil_kredensial_dari_db
kredensial_dict = ambil_kredensial_dari_db()

perangkat_juniper = [{
    'device_type': 'juniper_junos',
    'host': kred['ip'],
    'username': kred['username'],
    'password': kred['password'],
    'port': 22,
} for key, kred in kredensial_dict.items() if 'ip_perangkat_juniper' in key]

perangkat_hp_comware = [{
    'device_type': 'hp_comware',
    'host': kred['ip'],
    'username': kred['username'],
    'password': kred['password'],
    'port': 22,
} for key, kred in kredensial_dict.items() if 'ip_perangkat_h3c' in key]


# Fungsi untuk mendapatkan tanggal saat ini dalam format yang diinginkan
def get_current_date_format():
    return datetime.now().strftime("%d %B %Y")

# Fungsi untuk backup konfigurasi perangkat
def backup_konfigurasi(perangkat):
    for p in perangkat:
        # Membuat koneksi ke perangkat
        koneksi = ConnectHandler(**p)
        
        # Mengambil hostname dari perangkat
        hostname = koneksi.find_prompt().strip('<').strip('>')
        
        # Mengirim perintah untuk menampilkan konfigurasi
        if p['device_type'] == 'juniper_junos':
            output = koneksi.send_command('show configuration | no-more')
        elif p['device_type'] == 'hp_comware':
            output = koneksi.send_command('display current-configuration')
        
        # Membuat direktori berdasarkan device_type
        device_dir = f"{backup_dir}/{get_current_date_format()}/{p['device_type']}"
        buat_direktori(device_dir)
        
        # Menyimpan output ke file dalam direktori yang sesuai
        nama_file = f"{device_dir}/{hostname}.txt"
        with open(nama_file, 'w') as file:
            file.write(output)
        
        # Menutup koneksi
        koneksi.disconnect()
        print(f"Backup {p['device_type']} berhasil disimpan di {nama_file}")


if __name__ == "__main__":
    # Melakukan backup untuk masing-masing perangkat
    backup_konfigurasi(perangkat_juniper)
    backup_konfigurasi(perangkat_hp_comware)
