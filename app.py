# app.py - 로그인 기능이 추가된 Flask 챗봇 애플리케이션
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
import os
import requests
from datetime import datetime
import time
from werkzeug.utils import secure_filename
from document_processor import DocumentProcessor, QuestionAnalyzer
import traceback
from functools import wraps
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-change-in-production-' + secrets.token_hex(16))

# 관리자 계정 설정 (환경변수 또는 기본값)
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

# 비밀번호 해시화 (보안 강화)
ADMIN_PASSWORD_HASH = hashlib.sha256(ADMIN_PASSWORD.encode()).hexdigest()

# 설정
UPLOAD_FOLDER = 'uploaded_documents'
ALLOWED_EXTENSIONS = {'pdf', 'docx', 'pptx', 'xlsx', 'xls'}
MAX_FILE_SIZE = 16 * 1024 * 1024  # 16MB

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 업로드 폴더 생성
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 전역 변수로 초기화 상태 추적
initialization_status = {
    'success': False,
    'error': None,
    'document_processor': None,
    'question_analyzer': None
}

def login_required(f):
    """로그인 필수 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session or not session['logged_in']:
            flash('관리자 로그인이 필요합니다.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def verify_password(password):
    """비밀번호 검증"""
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    return password_hash == ADMIN_PASSWORD_HASH

def initialize_processors():
    """문서 프로세서 안전 초기화"""
    global initialization_status
    
    try:
        print("=== 프로세서 초기화 시작 ===")
        
        # DocumentProcessor 초기화
        document_processor = DocumentProcessor(UPLOAD_FOLDER)
        question_analyzer = QuestionAnalyzer(document_processor)
        
        # 기존 문서 처리
        document_processor.initialize_existing_documents()
        
        initialization_status = {
            'success': True,
            'error': None,
            'document_processor': document_processor,
            'question_analyzer': question_analyzer
        }
        
        print("=== 프로세서 초기화 완료 ===")
        print(f"처리된 문서 수: {len(document_processor.documents)}")
        
    except Exception as e:
        error_msg = f"프로세서 초기화 실패: {e}"
        print(f"❌ {error_msg}")
        traceback.print_exc()
        
        initialization_status = {
            'success': False,
            'error': error_msg,
            'document_processor': None,
            'question_analyzer': None
        }

# 서버 시작시 초기화
initialize_processors()

def get_processors():
    """프로세서 가져오기 (재초기화 포함)"""
    if not initialization_status['success']:
        print("⚠️ 프로세서 재초기화 시도...")
        initialize_processors()
    
    return initialization_status['document_processor'], initialization_status['question_analyzer']

def allowed_file(filename):
    """허용된 파일 확장자 확인"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type_display(filename):
    """파일 확장자에 따른 표시명 반환"""
    ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
    type_mapping = {
        'pdf': 'PDF',
        'docx': 'Word',
        'pptx': 'PowerPoint',
        'xlsx': 'Excel',
        'xls': 'Excel (Legacy)'
    }
    return type_mapping.get(ext, 'Unknown')

@app.route('/')
def index():
    """메인 페이지"""
    try:
        document_processor, _ = get_processors()
        
        if document_processor:
            document_files = document_processor.get_uploaded_files()
            processed_files = document_processor.get_processed_files_info()
            supported_formats = list(document_processor.supported_extensions.values())
        else:
            document_files = []
            processed_files = []
            supported_formats = ['PDF']  # 기본값
        
        return render_template('index.html', 
                             document_files=document_files,
                             processed_files=processed_files,
                             supported_formats=supported_formats)
    except Exception as e:
        print(f"Index 페이지 오류: {e}")
        return render_template('index.html', 
                             document_files=[],
                             processed_files=[],
                             supported_formats=['PDF'])

@app.route('/login', methods=['GET', 'POST'])
def login():
    """관리자 로그인"""
    if request.method == 'POST':
        try:
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            
            print(f"로그인 시도: 사용자명='{username}'")
            
            # 입력값 검증
            if not username or not password:
                flash('사용자명과 비밀번호를 입력해주세요.', 'error')
                return render_template('login.html')
            
            # 계정 확인
            if username == ADMIN_USERNAME and verify_password(password):
                session['logged_in'] = True
                session['username'] = username
                session['login_time'] = datetime.now().isoformat()
                
                print(f"✅ 로그인 성공: {username}")
                flash('관리자 로그인에 성공했습니다.', 'success')
                
                # 원래 요청한 페이지로 리다이렉트 (있다면)
                next_page = request.args.get('next')
                if next_page:
                    return redirect(next_page)
                else:
                    return redirect(url_for('admin'))
            else:
                print(f"❌ 로그인 실패: {username}")
                flash('사용자명 또는 비밀번호가 올바르지 않습니다.', 'error')
                return render_template('login.html')
                
        except Exception as e:
            print(f"로그인 처리 오류: {e}")
            traceback.print_exc()
            flash('로그인 처리 중 오류가 발생했습니다.', 'error')
            return render_template('login.html')
    
    # GET 요청 또는 로그인 실패시 로그인 페이지 표시
    return render_template('login.html')

@app.route('/logout')
def logout():
    """로그아웃"""
    try:
        username = session.get('username', 'unknown')
        session.clear()
        print(f"로그아웃: {username}")
        flash('로그아웃되었습니다.', 'success')
    except Exception as e:
        print(f"로그아웃 오류: {e}")
        flash('로그아웃 처리 중 오류가 발생했습니다.', 'warning')
    
    return redirect(url_for('index'))

@app.route('/admin')
@login_required
def admin():
    """관리자 페이지 (로그인 필수)"""
    try:
        document_processor, _ = get_processors()
        
        if document_processor:
            document_files = document_processor.get_uploaded_files()
            processed_files = document_processor.get_processed_files_info()
            
            # 파일 형식별 통계
            file_type_stats = {}
            for file_info in processed_files:
                file_type = file_info['file_type']
                file_type_stats[file_type] = file_type_stats.get(file_type, 0) + 1
            
            supported_formats = list(document_processor.supported_extensions.values())
        else:
            document_files = []
            processed_files = []
            file_type_stats = {}
            supported_formats = ['PDF']
        
        allowed_extensions_list = list(ALLOWED_EXTENSIONS)
        
        # 로그인 정보 추가
        login_info = {
            'username': session.get('username', ''),
            'login_time': session.get('login_time', '')
        }
        
        return render_template('admin.html', 
                             document_files=document_files, 
                             processed_files=processed_files,
                             file_type_stats=file_type_stats,
                             supported_formats=supported_formats,
                             allowed_extensions=allowed_extensions_list,
                             login_info=login_info)
    except Exception as e:
        print(f"Admin 페이지 오류: {e}")
        traceback.print_exc()
        flash(f'관리자 페이지 로딩 오류: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """문서 파일 업로드 (로그인 필수)"""
    try:
        print("=== 파일 업로드 시작 ===")
        
        document_processor, _ = get_processors()
        if not document_processor:
            flash('시스템 초기화 오류가 발생했습니다.', 'error')
            return redirect(url_for('admin'))
        
        if 'file' not in request.files:
            flash('파일이 선택되지 않았습니다.', 'error')
            return redirect(url_for('admin'))
        
        file = request.files['file']
        if file.filename == '':
            flash('파일이 선택되지 않았습니다.', 'error')
            return redirect(url_for('admin'))
        
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_type = get_file_type_display(filename)
            username = session.get('username', 'unknown')
            print(f"업로드 파일: {filename} ({file_type}) - 업로드자: {username}")
            
            # 중복 파일명 처리
            if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)):
                name, ext = os.path.splitext(filename)
                counter = 1
                while os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], f"{name}_{counter}{ext}")):
                    counter += 1
                filename = f"{name}_{counter}{ext}"
                print(f"중복 방지 파일명: {filename}")
            
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            print(f"파일 저장: {filepath} ({os.path.getsize(filepath)} bytes)")
            
            # 문서 처리
            print(f"{file_type} 문서 처리 시작...")
            success = document_processor.process_document(filepath)
            
            if success:
                doc_count = len(document_processor.documents)
                chunks_count = len([doc for doc in document_processor.documents if doc['filename'] == filename])
                print(f"✓ 처리 완료: {chunks_count}개 청크 생성 (전체: {doc_count}개)")
                flash(f'{file_type} 파일 "{filename}"이 성공적으로 처리되었습니다. ({chunks_count}개 청크)', 'success')
            else:
                print(f"✗ {file_type} 문서 처리 실패")
                flash(f'파일 업로드는 성공했지만 {file_type} 문서 처리 중 오류가 발생했습니다.', 'warning')
            
            return redirect(url_for('admin'))
        else:
            allowed_formats = ', '.join(ALLOWED_EXTENSIONS)
            flash(f'지원되는 파일 형식만 업로드 가능합니다. (지원 형식: {allowed_formats})', 'error')
            return redirect(url_for('admin'))
            
    except Exception as e:
        print(f"❌ 업로드 오류: {e}")
        traceback.print_exc()
        flash(f'업로드 중 오류가 발생했습니다: {str(e)}', 'error')
        return redirect(url_for('admin'))

@app.route('/delete/<filename>', methods=['POST'])
@login_required
def delete_file(filename):
    """문서 파일 삭제 (로그인 필수)"""
    try:
        document_processor, _ = get_processors()
        if not document_processor:
            flash('시스템 오류가 발생했습니다.', 'error')
            return redirect(url_for('admin'))
        
        file_type = get_file_type_display(filename)
        username = session.get('username', 'unknown')
        print(f"파일 삭제 요청: {filename} ({file_type}) - 요청자: {username}")
        
        success = document_processor.delete_file(filename)
        if success:
            flash(f'{file_type} 파일 "{filename}"이 삭제되었습니다.', 'success')
        else:
            flash(f'파일 삭제에 실패했습니다.', 'error')
    except Exception as e:
        print(f"❌ 삭제 오류: {e}")
        flash(f'삭제 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/reprocess', methods=['POST'])
@login_required
def reprocess_all():
    """모든 문서 파일 재처리 (로그인 필수)"""
    try:
        document_processor, _ = get_processors()
        if not document_processor:
            flash('시스템 오류가 발생했습니다.', 'error')
            return redirect(url_for('admin'))
        
        username = session.get('username', 'unknown')
        print(f"=== 모든 문서 재처리 시작 - 요청자: {username} ===")
        
        success = document_processor.reprocess_all_documents()
        if success:
            doc_count = len(document_processor.documents)
            flash(f'모든 문서 파일이 재처리되었습니다. (총 {doc_count}개 청크)', 'success')
        else:
            flash('재처리 중 일부 오류가 발생했습니다.', 'warning')
    except Exception as e:
        print(f"❌ 재처리 오류: {e}")
        traceback.print_exc()
        flash(f'재처리 중 오류가 발생했습니다: {str(e)}', 'error')
    
    return redirect(url_for('admin'))

@app.route('/api/chat', methods=['POST'])
def chat():
    """챗봇 대화 API (로그인 불필요)"""
    try:
        print("\n" + "="*50)
        print("=== 채팅 API 호출 ===")
        
        # 프로세서 확인
        document_processor, question_analyzer = get_processors()
        if not document_processor or not question_analyzer:
            error_msg = f"시스템 초기화 오류: {initialization_status.get('error', '알 수 없는 오류')}"
            print(f"❌ {error_msg}")
            return jsonify({
                'success': False,
                'message': f'시스템 오류가 발생했습니다: {error_msg}'
            })
        
        # 요청 데이터 확인
        data = request.get_json()
        if not data:
            print("❌ JSON 데이터 없음")
            return jsonify({
                'success': False,
                'message': '잘못된 요청입니다.'
            })
        
        question = data.get('message', '').strip()
        print(f"📝 받은 질문: '{question}'")
        
        if not question:
            print("❌ 빈 질문")
            return jsonify({
                'success': False,
                'message': '질문을 입력해주세요.'
            })
        
        # 문서 상태 확인
        doc_count = len(document_processor.documents)
        processed_files = document_processor.get_processed_files_info()
        print(f"📊 현재 상태:")
        print(f"  - 문서 청크 수: {doc_count}")
        print(f"  - 처리된 파일 수: {len(processed_files)}")
        
        # 문서가 없는 경우
        if not document_processor.has_processed_documents():
            print("⚠️ 처리된 문서 없음")
            supported_formats = ', '.join(document_processor.supported_extensions.values())
            return jsonify({
                'success': True,
                'message': f'''📋 **안내사항**

현재 처리된 문서가 없습니다. 

**관리자 기능**을 통해 문서 파일을 업로드해주세요.

**📁 지원 파일 형식**: {supported_formats}

💡 문서 파일을 업로드하면 해당 문서의 내용을 기반으로 정확한 답변을 제공할 수 있습니다.

**🔧 문제 해결 방법:**
1. 관리자 페이지에서 로그인 후 파일 업로드
2. 파일이 "처리됨" 상태인지 확인
3. 청크 수가 0이 아닌지 확인''',
                'timestamp': datetime.now().strftime('%H:%M:%S')
            })
        
        # 질문 분석 및 답변 생성
        print("🔍 질문 분석 시작...")
        start_time = time.time()
        
        try:
            answer = question_analyzer.analyze_question(question)
            processing_time = time.time() - start_time
            print(f"✅ 답변 생성 완료 ({processing_time:.2f}초)")
            print(f"📤 답변 길이: {len(answer)}자")
            
            # 디버그 정보 생성
            file_type_stats = {}
            for doc in document_processor.documents:
                file_type = doc.get('file_type', 'Unknown')
                file_type_stats[file_type] = file_type_stats.get(file_type, 0) + 1
            
            debug_info = f"문서 청크: {doc_count}개"
            if file_type_stats:
                stats_str = ", ".join([f"{ft}: {count}" for ft, count in file_type_stats.items()])
                debug_info += f" ({stats_str})"
            
            print("="*50)
            
            return jsonify({
                'success': True,
                'message': answer,
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'debug_info': debug_info,
                'processing_time': f"{processing_time:.2f}초"
            })
            
        except Exception as e:
            print(f"❌ 질문 분석 오류: {e}")
            traceback.print_exc()
            return jsonify({
                'success': False,
                'message': f'질문 처리 중 오류가 발생했습니다: {str(e)}'
            })
        
    except Exception as e:
        print(f"❌ Chat API 전체 오류: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': '서버 오류가 발생했습니다. 콘솔을 확인해주세요.'
        })

@app.route('/api/status')
def status():
    """시스템 상태 API (로그인 불필요)"""
    try:
        document_processor, _ = get_processors()
        
        if document_processor:
            document_files = document_processor.get_uploaded_files()
            processed_files = document_processor.get_processed_files_info()
            
            # 파일 타입별 통계
            file_type_stats = {}
            for file_info in processed_files:
                file_type = file_info['file_type']
                file_type_stats[file_type] = file_type_stats.get(file_type, 0) + 1
            
            return jsonify({
                'status': 'connected' if document_files else 'no_files',
                'total_files': len(document_files),
                'processed_files': len(processed_files),
                'total_chunks': len(document_processor.documents),
                'file_type_stats': file_type_stats,
                'supported_formats': list(document_processor.supported_extensions.values()),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_loaded': len(processed_files) > 0,
                'initialization_success': initialization_status['success'],
                'admin_logged_in': session.get('logged_in', False)
            })
        else:
            return jsonify({
                'status': 'error',
                'message': initialization_status.get('error', '초기화 실패'),
                'initialization_success': False,
                'admin_logged_in': False
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'initialization_success': False,
            'admin_logged_in': False
        })

@app.route('/api/files')
def get_files():
    """업로드된 파일 목록 API (로그인 불필요)"""
    try:
        document_processor, _ = get_processors()
        
        if document_processor:
            files_info = document_processor.get_processed_files_info()
            
            # 추가 정보 포함
            for file_info in files_info:
                file_info['display_type'] = file_info['file_type']
                file_info['size_mb'] = round(file_info['file_size'] / (1024 * 1024), 2)
            
            return jsonify({
                'success': True,
                'files': files_info,
                'total_files': len(files_info),
                'total_chunks': len(document_processor.documents),
                'supported_formats': list(document_processor.supported_extensions.values())
            })
        else:
            return jsonify({
                'success': False,
                'error': initialization_status.get('error', '시스템 초기화 실패')
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/test-chat', methods=['POST'])
def test_chat():
    """간단한 채팅 테스트 API (로그인 불필요)"""
    try:
        print("🧪 테스트 채팅 API 호출됨")
        
        data = request.get_json()
        message = data.get('message', '') if data else ''
        
        print(f"📨 받은 메시지: '{message}'")
        
        # 간단한 응답 반환 (문서 처리 없이)
        if not message:
            response = "테스트: 메시지가 비어있습니다."
        elif "안녕" in message or "hello" in message.lower():
            response = "테스트: 안녕하세요! 테스트 응답입니다. 시스템이 정상 작동 중입니다."
        else:
            response = f"테스트: '{message}' 메시지를 잘 받았습니다. API 연결이 정상입니다."
        
        result = {
            'success': True,
            'message': response,
            'timestamp': datetime.now().strftime('%H:%M:%S'),
            'test_mode': True
        }
        
        print(f"📤 응답 전송: {result}")
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ 테스트 채팅 오류: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'message': f'테스트 오류: {str(e)}',
            'test_mode': True
        })

@app.route('/api/debug')
def debug_info():
    """디버그 정보 API (로그인 불필요)"""
    try:
        document_processor, question_analyzer = get_processors()
        
        # JSON 직렬화 가능한 데이터만 포함
        debug_data = {
            'initialization_success': initialization_status['success'],
            'initialization_error': initialization_status['error'],
            'has_document_processor': document_processor is not None,
            'has_question_analyzer': question_analyzer is not None,
            'document_count': len(document_processor.documents) if document_processor else 0,
            'metadata_count': len(document_processor.metadata) if document_processor else 0,
            'upload_folder_exists': os.path.exists(UPLOAD_FOLDER),
            'upload_folder_files': os.listdir(UPLOAD_FOLDER) if os.path.exists(UPLOAD_FOLDER) else [],
            'supported_extensions': list(document_processor.supported_extensions.values()) if document_processor else [],
            'embeddings_available': (document_processor.embeddings is not None) if document_processor else False,
            'admin_logged_in': session.get('logged_in', False),
            'session_data': {
                'username': session.get('username', None),
                'login_time': session.get('login_time', None)
            }
        }
        
        # 처리된 파일 정보 추가
        if document_processor:
            try:
                processed_files = document_processor.get_processed_files_info()
                debug_data['processed_files'] = processed_files
                debug_data['processed_files_count'] = len(processed_files)
            except Exception as e:
                debug_data['processed_files_error'] = str(e)
        
        return jsonify(debug_data)
    except Exception as e:
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        })

# 오류 처리
@app.errorhandler(413)
def too_large(e):
    flash(f'파일 크기가 너무 큽니다. 최대 {MAX_FILE_SIZE // (1024*1024)}MB까지 업로드 가능합니다.', 'error')
    return redirect(url_for('admin'))

@app.errorhandler(404)
def not_found(e):
    return f"페이지를 찾을 수 없습니다: {request.url}", 404

@app.errorhandler(500)
def server_error(e):
    print(f"500 오류: {e}")
    traceback.print_exc()
    return f"서버 오류가 발생했습니다: {str(e)}", 500

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 Flask 서버 시작")
    print("="*60)
    
    # 관리자 계정 정보 출력
    print(f"🔐 관리자 계정 설정:")
    print(f"   사용자명: {ADMIN_USERNAME}")
    print(f"   비밀번호: {'*' * len(ADMIN_PASSWORD)}")
    print(f"   (환경변수 ADMIN_USERNAME, ADMIN_PASSWORD로 변경 가능)")
    
    if initialization_status['success']:
        processed_count = len(initialization_status['document_processor'].get_processed_files_info())
        chunk_count = len(initialization_status['document_processor'].documents)
        print(f"✅ 초기화 성공! 처리된 파일: {processed_count}개, 청크: {chunk_count}개")
        
        if processed_count > 0:
            print("\n📁 처리된 파일 목록:")
            for file_info in initialization_status['document_processor'].get_processed_files_info():
                print(f"  - {file_info['filename']} ({file_info['file_type']}) - {file_info['chunks_count']} 청크")
    else:
        print(f"❌ 초기화 실패: {initialization_status['error']}")
    
    # 지원 파일 형식 정보 출력
    if initialization_status['document_processor']:
        supported_formats = ', '.join(initialization_status['document_processor'].supported_extensions.values())
        print(f"\n📋 지원 파일 형식: {supported_formats}")
    
    print(f"🌐 서버 주소: http://localhost:5000")
    print(f"🔧 관리자 페이지: http://localhost:5000/admin")
    print(f"🔒 로그인 페이지: http://localhost:5000/login")
    print(f"🐛 디버그 정보: http://localhost:5000/api/debug")
    print("="*60)
    
    # Flask 서버 실행
    app.run(host='0.0.0.0', port=5000, debug=True)