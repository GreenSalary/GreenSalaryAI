# 1. Python 기반 이미지 사용
FROM python:3.9-slim

# 2. 시스템 패키지 업데이트 및 필요한 패키지 설치 (Chromium, Chromedriver)
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. 작업 디렉토리 설정
WORKDIR /app

# 4. 요구 사항 파일을 컨테이너로 복사
COPY requirements.txt /app/

# 5. Python 패키지 설치
RUN pip install --no-cache-dir -r requirements.txt

# 6. 애플리케이션 파일 복사
COPY . /app/

# 7. 환경 변수 설정 (필요 시, 외부 환경 변수 추가)
ENV DISPLAY=:99

# 8. FastAPI 애플리케이션 실행 (Uvicorn 사용)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
