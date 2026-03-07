# Pharma Intelligence - Competitive Monitoring Dashboard

Pharma Competitive Intelligence 플랫폼. ClinicalTrials.gov, FDA, EMA 데이터 수집 및 파이프라인 영향 분석.

## 파일 구성

| 파일 | 설명 |
|------|------|
| `pharma_intelligence_app.py` | 통합 Python 앱 (Flask, 모든 모듈 포함) |
| `pharma_intelligence_dashboard.html` | 대시보드 UI (단독 HTML) |
| `requirements.txt` | Python 의존성 |

## 설치 및 실행

```bash
pip install -r requirements.txt
python pharma_intelligence_app.py
```

브라우저에서 **http://127.0.0.1:5001** 접속.

## 기능

- **검색**: ClinicalTrials.gov, FDA Label, EMA 데이터 조회
- **뉴스**: Biopharma Dive, Fierce Pharma 뉴스 수집
- **파이프라인 분석**: Boehringer Ingelheim 파이프라인 영향 평가
- **데모**: 샘플 데이터로 기능 확인
