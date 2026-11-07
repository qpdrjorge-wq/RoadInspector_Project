import sqlite3
import os

# This forces the path to always be in the main project root, no matter which file calls it
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "inspections.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS Reports (
            Report_ID INTEGER PRIMARY KEY AUTOINCREMENT,
            Date_Captured DATETIME DEFAULT CURRENT_TIMESTAMP,
            Latitude REAL,
            Longitude REAL,
            Hazard_Class TEXT,
            Severity TEXT,
            Status TEXT DEFAULT 'Pending',
            Image_Path TEXT
        )
    ''')
    conn.commit()
    conn.close()

def insert_report(hazard_class, severity, lat=None, lon=None, image_path=None):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO Reports (Latitude, Longitude, Hazard_Class, Severity, Image_Path)
        VALUES (?, ?, ?, ?, ?)
    ''', (lat, lon, hazard_class, severity, image_path))
    conn.commit()
    conn.close()