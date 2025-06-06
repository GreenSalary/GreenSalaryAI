from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
import os
import time
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from openai import OpenAI
from dotenv import load_dotenv

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Hello! FastAPI 서버가 정상 작동 중입니다."}

class ContractRequest(BaseModel):
    contract_title: str
    influencer_name: str
    site_url: str
    image_url: str
    keywords: List[str]
    conditions: List[str]
    media_text: int
    media_image: int

def crawl_naver_blog(url: str) -> Dict[str, Any]:
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        driver.get(url)
        time.sleep(3)
        driver.switch_to.frame("mainFrame")
        time.sleep(1)

        try:
            content_container = driver.find_element(By.CSS_SELECTOR, ".se-main-container")
        except:
            content_container = driver.find_element(By.CSS_SELECTOR, "#postViewArea")

        content = content_container.text
        images = content_container.find_elements(By.TAG_NAME, "img")

        return {
            "content": content,
            "image_count": len(images),
            "char_count": len(content)
        }

    except Exception as e:
        raise RuntimeError(f"Crawling error: {e}")

    finally:
        driver.quit()

def check_keywords(content: str, keywords: List[str]) -> bool:
    return all(kw.lower() in content.lower() for kw in keywords)

def get_missing_keywords(content: str, keywords: List[str]) -> List[str]:
    content_lower = content.lower()
    return [kw for kw in keywords if kw.lower() not in content_lower]

def analyze_with_gpt(content: str, conditions: List[str]) -> Dict[str, Any]:
    prompt = f"""
다음은 계약 조건입니다:
{chr(10).join(f"- {c}" for c in conditions)}

아래 블로그 본문에서 각 조건이 충족되었는지 판단해 주세요. 
각 조건당 "Yes" 또는 "No"만 반환해 주세요. 다음 예시처럼:

조건: [조건 내용] → Yes 또는 No
    """
    response = client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "당신은 계약 이행 분석 전문가입니다."},
            {"role": "user", "content": prompt + "\n\n블로그 본문:\n" + content}
        ],
        temperature=0,
    )
    result_text = response.choices[0].message.content

    condition_results = []
    all_yes = True
    for line in result_text.splitlines():
        if "→" in line:
            try:
                cond_text, res = line.split("→")
                cond_text = cond_text.replace("조건:", "").strip()
                res = res.strip()
                condition_results.append({
                    "condition": cond_text,
                    "result": res
                })
                if res.lower() != "yes":
                    all_yes = False
            except:
                pass

    return {
        "all_passed": all_yes,
        "details": condition_results
    }

def create_pdf_report(file_path: str, contract_title: str, influencer_name: str, site_url: str,
                      keyword_test: bool, condition_test: bool, word_count_test: bool, image_count_test: bool,
                      condition_details: list, missing_keywords: List[str]):
    # 한글 폰트 등록 (한 번만 등록하면 됨)
    if 'NanumGothic' not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont('NanumGothic', 'NanumGothic-Regular.ttf'))

    doc = SimpleDocTemplate(file_path, pagesize=A4)
    styles = getSampleStyleSheet()

    # 모든 기본 스타일에 NanumGothic 폰트 지정
    for style_name in styles.byName:
        styles[style_name].fontName = 'NanumGothic'

    story = []

    story.append(Paragraph(f"<b>광고 이름</b><br/>{contract_title}", styles['Title']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>인플루언서 이름</b><br/>{influencer_name}", styles['Normal']))
    story.append(Spacer(1, 12))
    story.append(Paragraph(f"<b>URL</b><br/>{site_url}", styles['Normal']))
    story.append(Spacer(1, 24))

    data = [
        ["검사 항목", "충족 여부"],
        ["키워드 포함", "O" if keyword_test else "X"],
        ["세부 조건", "O" if condition_test else "X"],
        ["글자 수", "O" if word_count_test else "X"],
        ["이미지 수", "O" if image_count_test else "X"],
    ]

    table = Table(data, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('TEXTCOLOR', (0,0), (-1,0), colors.black),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN',(1,1),(-1,-1),'CENTER'),
        ('FONTNAME', (0,0), (-1,-1), 'NanumGothic'),  # 폰트 지정(헤더+내용)
    ]))

    story.append(table)
    story.append(Spacer(1, 24))

    # 누락된 키워드가 있을 경우 출력
    if not keyword_test and missing_keywords:
        story.append(Spacer(1, 12))
        story.append(Paragraph("<b>누락된 키워드</b>", styles['Heading3']))
        story.append(Spacer(1, 6))
        story.append(Paragraph(", ".join(missing_keywords), styles['Normal']))
        story.append(Spacer(1, 12))

    story.append(Paragraph("<b>조건 상세 분석</b>", styles['Heading2']))
    story.append(Spacer(1, 12))

    for idx, cond in enumerate(condition_details, 1):
        cond_text = cond.get("condition", "")
        result = cond.get("result", "")
        symbol = "✅" if result.lower() == "yes" else "❌"
        story.append(Paragraph(f"{idx}. 조건: {cond_text} → {symbol} ({result})", styles['Normal']))
        story.append(Spacer(1, 6))

    doc.build(story)

@app.post("/analyze")
def analyze_contract(data: ContractRequest):
    try:
        blog_data = crawl_naver_blog(data.site_url)

        keyword_test = check_keywords(blog_data["content"], data.keywords)
        missing_keywords = get_missing_keywords(blog_data["content"], data.keywords)
        word_count_test = blog_data["char_count"] >= data.media_text
        image_count_test = blog_data["image_count"] >= data.media_image
        gpt_result = analyze_with_gpt(blog_data["content"], data.conditions)

        os.makedirs("./results", exist_ok=True)
        pdf_filename = f"result_{uuid.uuid4().hex}.pdf"
        pdf_path = os.path.join("./results", pdf_filename)

        create_pdf_report(
            pdf_path,
            data.contract_title,
            data.influencer_name,
            data.site_url,
            keyword_test,
            gpt_result["all_passed"],
            word_count_test,
            image_count_test,
            gpt_result["details"],
            missing_keywords
        )

        # ★ PDF 경로를 로컬 경로로 그대로 반환
        return {
            "keywordTest": keyword_test,
            "conditionTest": gpt_result["all_passed"],
            "conditionDetail": gpt_result["details"],
            "wordCountTest": word_count_test,
            "imageCountTest": image_count_test,
            "pdf_url": pdf_path,  # 예: ./results/result_xxx.pdf
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
