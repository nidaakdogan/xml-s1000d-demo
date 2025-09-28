#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
S1000D Veri Modülü Üretici - Web Arayüzü
Flask web uygulaması ile PDF'den XML'e dönüştürme
"""

from flask import Flask, render_template, request, jsonify, send_file
import os
import tempfile
import re
from werkzeug.utils import secure_filename
from s1000d_full_processor import S1000DFullProcessor
from s1000d_smart_processor import S1000DSmartProcessor

def extract_module_info_from_xml(xml_content):
    """XML içeriğinden modül bilgilerini çıkarır."""
    module_info = {
        'title': 'Bilinmeyen Başlık',
        'applicability': 'General',
        'source_pages': '1',
        'has_graphics': False,
        'content_summary': 'İçerik özeti mevcut değil',
        'module_code': 'DMC-GN016'
    }
    
    try:
        # Title çıkar
        title_match = re.search(r'<title>(.*?)</title>', xml_content, re.DOTALL)
        if title_match:
            module_info['title'] = title_match.group(1).strip()
        
        # Applicability çıkar
        applic_match = re.search(r'<applicAssert[^>]*applicPropertyValue="([^"]*)"', xml_content)
        if applic_match:
            module_info['applicability'] = applic_match.group(1)
        
        # Source pages çıkar
        source_match = re.search(r'<moduleInfo[^>]*sourcePage="([^"]*)"', xml_content)
        if source_match:
            module_info['source_pages'] = source_match.group(1)
        
        # Graphics kontrolü
        graphics_match = re.search(r'<moduleInfo[^>]*hasGraphics="([^"]*)"', xml_content)
        if graphics_match:
            module_info['has_graphics'] = graphics_match.group(1).lower() == 'true'
        
        # Content summary çıkar
        summary_match = re.search(r'<moduleInfo[^>]*contentSummary="([^"]*)"', xml_content)
        if summary_match:
            module_info['content_summary'] = summary_match.group(1)
        
        # Module code çıkar
        code_match = re.search(r'<dmCode[^>]*infoCode="([^"]*)"', xml_content)
        if code_match:
            module_info['module_code'] = code_match.group(1)
            
    except Exception as e:
        print(f"XML bilgi çıkarma hatası: {e}")
    
    return module_info

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Geçici klasör oluştur
TEMP_DIR = "temp"
UPLOAD_DIR = os.path.join(TEMP_DIR, "uploads")
OUTPUT_DIR = os.path.join(TEMP_DIR, "output")

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

@app.route('/')
def index():
    """Ana sayfa"""
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_pdf():
    """PDF'yi S1000D modüllerine dönüştür"""
    import time
    start_time = time.time()
    
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Dosya seçilmedi'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Dosya seçilmedi'}), 400
        
        # Dosya tipini kontrol et (daha esnek validasyon)
        filename = file.filename.lower() if file.filename else ''
        file_type = file.content_type.lower() if file.content_type else ''
        
        # PDF kontrolü - uzantı, MIME type veya boş type (Windows'ta sık karşılaşılan durum)
        is_pdf = (filename.endswith('.pdf') or 
                 file_type == 'application/pdf' or 
                 file_type == '' or
                 'pdf' in file_type or
                 file_type == 'text/html')  # Windows bazen PDF'leri HTML olarak tanır
        
        if not is_pdf:
            return jsonify({'error': f'Sadece PDF dosyaları kabul edilir. Dosya tipi: {file_type}'}), 400
        
        # Dosyayı kaydet
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_DIR, filename)
        file.save(filepath)
        
        # Dosya boyutunu kontrol et
        file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
        print(f"📁 Yüklenen dosya: {filename} ({file_size:.1f} MB)")
        
        # Smart Processor kullan (ana başlık bazlı)
        processor = S1000DSmartProcessor()
        processor.input_dir = UPLOAD_DIR
        
        # Modülleri oluştur
        success = processor.process_smart_pdf(filename)
        
        if success:
            # Oluşturulan modül sayısını say ve detaylı bilgileri al
            modules_dir = processor.modules_dir
            xml_files = [f for f in os.listdir(modules_dir) if f.endswith('.xml') and f.startswith('dm')]
            module_count = len(xml_files)
            
            # Tüm modüllerin detaylı bilgilerini oku
            detailed_modules = []
            for xml_file in sorted(xml_files):
                xml_path = os.path.join(modules_dir, xml_file)
                try:
                    with open(xml_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        
                        # XML'den modül bilgilerini çıkar
                        module_info = extract_module_info_from_xml(content)
                        module_info['filename'] = xml_file
                        detailed_modules.append(module_info)
                        
                except Exception as e:
                    print(f"Modül okuma hatası {xml_file}: {e}")
            
            # İlk 5 modülü örnek olarak al
            sample_modules = detailed_modules[:5]
            
            # İşlem süresini hesapla
            processing_time = round(time.time() - start_time, 2)
            
            return jsonify({
                'success': True,
                'message': f'PDF başarıyla {module_count} S1000D modülüne dönüştürüldü! (Ana başlık bazlı)',
                'module_count': module_count,
                'sample_modules': sample_modules,
                'all_modules': detailed_modules,  # Tüm modüllerin detaylı bilgileri
                'download_url': '/download_modules',
                'optimization': f'535 XML yerine {module_count} optimize edilmiş modül',
                'processing_time': f'{processing_time} saniye'
            })
        else:
            return jsonify({'error': 'Dönüştürme işlemi başarısız'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Hata: {str(e)}'}), 500

@app.route('/download/<filename>')
def download_file(filename):
    """XML dosyasını indir"""
    filepath = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath, as_attachment=True)
    else:
        return jsonify({'error': 'Dosya bulunamadı'}), 404

@app.route('/download_modules')
def download_modules():
    """Tüm modülleri ZIP olarak indir"""
    import zipfile
    import io
    
    try:
        # Modules klasöründeki tüm XML dosyalarını ZIP'e ekle
        modules_dir = "modules"
        if not os.path.exists(modules_dir):
            return jsonify({'error': 'Modüller bulunamadı'}), 404
        
        # ZIP dosyası oluştur
        memory_file = io.BytesIO()
        with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(modules_dir):
                for file in files:
                    if file.endswith('.xml') or file.endswith('.txt'):
                        file_path = os.path.join(root, file)
                        zf.write(file_path, file)
        
        memory_file.seek(0)
        
        # Dinamik dosya adı oluştur
        from datetime import datetime
        current_date = datetime.now().strftime("%d_%m_%Y")
        zip_filename = f"moduller_{current_date}.zip"
        
        return send_file(
            memory_file,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        return jsonify({'error': f'ZIP oluşturma hatası: {str(e)}'}), 500

@app.route('/modules_list')
def modules_list():
    """Oluşturulan modüllerin listesini döndür"""
    try:
        modules_dir = "modules"
        if not os.path.exists(modules_dir):
            return jsonify({'error': 'Modüller bulunamadı'}), 404
        
        xml_files = [f for f in os.listdir(modules_dir) if f.endswith('.xml') and f.startswith('dm')]
        xml_files.sort()
        
        modules_info = []
        for xml_file in xml_files:
            xml_path = os.path.join(modules_dir, xml_file)
            file_size = os.path.getsize(xml_path)
            modules_info.append({
                'filename': xml_file,
                'size': file_size,
                'download_url': f'/download_module/{xml_file}'
            })
        
        return jsonify({
            'total_modules': len(modules_info),
            'modules': modules_info
        })
        
    except Exception as e:
        return jsonify({'error': f'Hata: {str(e)}'}), 500

@app.route('/download_module/<filename>')
def download_module(filename):
    """Tek bir modül dosyasını indir"""
    modules_dir = "modules"
    filepath = os.path.join(modules_dir, filename)
    
    if os.path.exists(filepath) and filename.endswith('.xml') and filename.startswith('dm'):
        return send_file(filepath, as_attachment=True)
    else:
        return jsonify({'error': 'Modül bulunamadı'}), 404

@app.route('/module_content/<filename>')
def get_module_content(filename):
    """XML modül içeriğini döndür"""
    modules_dir = "modules"
    filepath = os.path.join(modules_dir, filename)
    
    if os.path.exists(filepath) and filename.endswith('.xml') and filename.startswith('dm'):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                return content, 200, {'Content-Type': 'text/plain; charset=utf-8'}
        except Exception as e:
            return jsonify({'error': f'Dosya okuma hatası: {str(e)}'}), 500
    else:
        return jsonify({'error': 'Modül bulunamadı'}), 404

if __name__ == '__main__':
    print("🚀 S1000D Veri Modülü Üretici Web Arayüzü başlatılıyor...")
    print("📱 Tarayıcınızda http://localhost:5000 adresini açın")
    app.run(debug=True, host='0.0.0.0', port=5000)
