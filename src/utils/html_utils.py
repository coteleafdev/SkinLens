"""
html_utils.py — HTML 파일 처리 유틸리티 모듈

HTML 보고서 생성 및 이미지 처리에 대한 재사용 가능한 유틸리티 함수를 제공합니다.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional


def image_to_base64(image_path: str | Path, max_size: tuple[int, int] = (800, 800)) -> str:
    """이미지를 base64로 인코딩하여 HTML에 임베드할 수 있는 형식으로 변환합니다.
    
    Args:
        image_path: 이미지 파일 경로
        max_size: 최대 이미지 크기 (width, height)
    
    Returns:
        base64로 인코딩된 이미지 데이터 URI (data:image/...;base64,...)
    """
    try:
        from PIL import Image
    except ImportError:
        raise ImportError("Pillow 라이브러리가 필요합니다. 설치: pip install Pillow")
    
    image_path = Path(image_path)
    if not image_path.exists():
        raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")
    
    # 이미지 로드 및 크기 조정
    with Image.open(image_path) as img:
        # 원본 비율 유지하며 크기 조정
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # PNG로 변환 (투명도 지원)
        import io
        buffer = io.BytesIO()
        img.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        
        # Base64 인코딩
        image_data = base64.b64encode(buffer.read()).decode('utf-8')
        return f"data:image/png;base64,{image_data}"


def generate_html_report(
    title: str,
    original_image_uri: str,
    restored_image_uri: str,
    table_data: list[list[str]],
    llm_overall_opinion: str,
    llm_recommendations: list[str],
    matched_products: list[dict],
    metric_opinions: dict[str, str],
    timestamp: str,
    orig_llm_overall_score: Optional[float] = None,
    ref_llm_overall_score: Optional[float] = None,
    prescription: Optional[dict] = None,
    active_mixes: Optional[dict] = None,
    pcr_mixes: Optional[dict] = None,
) -> str:
    """HTML 보고서를 생성합니다.
    
    Args:
        title: 보고서 제목
        original_image_uri: 원본 이미지 데이터 URI
        restored_image_uri: 복원 이미지 데이터 URI
        table_data: 테이블 데이터 (2D 리스트)
        llm_overall_opinion: AI 종합 소견
        llm_recommendations: AI 추천 사항 리스트
        matched_products: 매칭된 제품 정보 리스트
        metric_opinions: 항목별 AI 소견 딕셔너리
        timestamp: 타임스탬프
        orig_llm_overall_score: 원본 이미지 AI 측정 피부건강지수
        ref_llm_overall_score: 기준 이미지 AI 측정 피부건강지수
        prescription: 처방전 정보 딕셔너리
        active_mixes: 활성 믹스 정보 딕셔너리 (M01-M13)
        pcr_mixes: PCR 믹스 정보 딕셔너리 (PM01-PM07)
    
    Returns:
        HTML 문자열
    """
    html_template = """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Malgun Gothic', '맑은 고딕', sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #f5f5f5;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        
        h1 {{
            color: #2c3e50;
            text-align: center;
            margin-bottom: 10px;
            font-size: 28px;
        }}
        
        .timestamp {{
            text-align: center;
            color: #7f8c8d;
            margin-bottom: 30px;
            font-size: 14px;
        }}
        
        .images-section {{
            display: flex;
            justify-content: space-around;
            margin-bottom: 30px;
            gap: 20px;
        }}
        
        .image-container {{
            flex: 1;
            text-align: center;
        }}
        
        .image-container img {{
            max-width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        
        .image-label {{
            margin-top: 10px;
            font-weight: bold;
            color: #34495e;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
            background-color: white;
        }}
        
        th {{
            background-color: #3498db;
            color: white;
            padding: 12px;
            text-align: center;
            font-weight: bold;
        }}
        
        td {{
            padding: 10px;
            text-align: center;
            border-bottom: 1px solid #ecf0f1;
        }}
        
        tr:nth-child(even) {{
            background-color: #f8f9fa;
        }}
        
        tr:hover {{
            background-color: #e8f4f8;
        }}
        
        .section-title {{
            color: #2c3e50;
            border-bottom: 2px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 20px;
            font-size: 20px;
        }}
        
        .opinion-text {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            line-height: 1.8;
        }}
        
        .recommendations {{
            background-color: #fff3cd;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 4px solid #ffc107;
        }}
        
        .recommendations ul {{
            list-style-position: inside;
            margin-top: 10px;
        }}
        
        .recommendations li {{
            margin-bottom: 8px;
        }}
        
        .products {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .product-card {{
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
        }}
        
        .product-name {{
            font-weight: bold;
            color: #2c3e50;
            margin-bottom: 10px;
            font-size: 16px;
        }}
        
        .product-category {{
            color: #7f8c8d;
            font-size: 14px;
            margin-bottom: 10px;
        }}
        
        .product-ingredients {{
            font-size: 13px;
            color: #555;
            margin-bottom: 10px;
        }}
        
        .product-match {{
            color: #27ae60;
            font-weight: bold;
            font-size: 14px;
        }}
        
        .metric-opinions {{
            background-color: #f0f8ff;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
            border-left: 4px solid #17a2b8;
        }}
        
        .metric-item {{
            margin-bottom: 15px;
            padding-bottom: 15px;
            border-bottom: 1px solid #e0e0e0;
        }}
        
        .metric-item:last-child {{
            border-bottom: none;
            margin-bottom: 0;
            padding-bottom: 0;
        }}
        
        .metric-name {{
            font-weight: bold;
            color: #2c3e50;
            font-size: 15px;
            margin-bottom: 5px;
        }}
        
        .metric-opinion {{
            color: #555;
            font-size: 14px;
            line-height: 1.6;
        }}
        
        @media print {{
            body {{
                background-color: white;
                padding: 0;
            }}
            
            .container {{
                box-shadow: none;
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>{title}</h1>
        <div class="timestamp">{timestamp}</div>
        
        <div class="images-section">
            <div class="image-container">
                <img src="{original_image_uri}" alt="원본 이미지">
                <div class="image-label">원본 이미지</div>
            </div>
            <div class="image-container">
                <img src="{restored_image_uri}" alt="기준 이미지">
                <div class="image-label">기준 이미지</div>
            </div>
        </div>
        
        <h2 class="section-title">AI 측정 피부건강지수</h2>
        <div class="opinion-text">
            <p><strong>원본 이미지 AI 측정 피부건강지수:</strong> {orig_llm_overall_score_display}</p>
            <p><strong>기준 이미지 AI 측정 피부건강지수:</strong> {ref_llm_overall_score_display}</p>
        </div>
        
        <h2 class="section-title">점수등급 기준</h2>
        <table>
            <thead>
                <tr>
                    <th>점수 범위</th>
                    <th>등급</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td>90 이상</td>
                    <td>매우 우수</td>
                </tr>
                <tr>
                    <td>80~90</td>
                    <td>우수</td>
                </tr>
                <tr>
                    <td>70~80</td>
                    <td>양호</td>
                </tr>
                <tr>
                    <td>60~70</td>
                    <td>집중케어 추천</td>
                </tr>
                <tr>
                    <td>60 미만</td>
                    <td>개선 필요</td>
                </tr>
            </tbody>
        </table>
        
        <h2 class="section-title">AI 측정 점수</h2>
        <table>
            <thead>
                <tr>
                    <th>항목명</th>
                    <th>AI 측정 점수 (원본)</th>
                    <th>AI 측정 점수 (기준)</th>
                </tr>
            </thead>
            <tbody>
                {table_rows}
            </tbody>
        </table>
        
        <h2 class="section-title">AI 종합 소견</h2>
        <div class="opinion-text">
            {llm_overall_opinion}
        </div>
        
        <h2 class="section-title">관리 권고사항</h2>
        <div class="recommendations">
            <ul>
                {recommendation_items}
            </ul>
        </div>
        
        <h2 class="section-title">원본 이미지 18개 항목별 AI 소견</h2>
        <div class="metric-opinions">
            {metric_opinions_section}
        </div>
        
        {products_section}
        
        <h2 class="section-title">처방전 (Prescription)</h2>
        <div class="prescription">
            {prescription_section}
        </div>
        
        <h2 class="section-title">활성 믹스 (M01-M13)</h2>
        <table>
            <thead>
                <tr>
                    <th>코드</th>
                    <th>이름</th>
                    <th>카테고리</th>
                    <th>설명</th>
                    <th>주요 성분</th>
                    <th>배합비</th>
                </tr>
            </thead>
            <tbody>
                {active_mixes_table}
            </tbody>
        </table>
        
        <h2 class="section-title">PCR 믹스 (PM01-PM07)</h2>
        <table>
            <thead>
                <tr>
                    <th>코드</th>
                    <th>이름</th>
                    <th>카테고리</th>
                    <th>설명</th>
                    <th>주요 성분</th>
                    <th>배합비</th>
                </tr>
            </thead>
            <tbody>
                {pcr_mixes_table}
            </tbody>
        </table>
    </div>
</body>
</html>"""
    
    # 테이블 행 생성
    table_rows = ""
    for row in table_data:
        table_rows += "<tr>"
        for cell in row:
            table_rows += f"<td>{cell}</td>"
        table_rows += "</tr>\n"
    
    # 추천 사항 리스트 생성
    recommendation_items = ""
    for rec in llm_recommendations:
        recommendation_items += f"<li>{rec}</li>\n"
    
    # 제품 섹션 생성
    products_section = ""
    if matched_products:
        products_section = '<h2 class="section-title">추천 제품</h2>\n<div class="products">\n'
        for product in matched_products:
            product_name = product.get("product_name", "알 수 없음")
            product_category = product.get("category", "알 수 없음")
            key_ingredients = product.get("key_ingredients", [])
            ingredients_str = ", ".join(key_ingredients) if key_ingredients else "정보 없음"
            match_score = product.get("match_score", 0)
            match_reason = product.get("match_reason", "")
            
            products_section += f"""
                <div class="product-card">
                    <div class="product-name">{product_name}</div>
                    <div class="product-category">카테고리: {product_category}</div>
                    <div class="product-ingredients">주요 성분: {ingredients_str}</div>
                    <div class="product-match">매칭 점수: {match_score:.2%}</div>
                    <div style="font-size: 12px; color: #666; margin-top: 5px;">{match_reason}</div>
                </div>
            """
        products_section += "</div>\n"
    
    # 항목별 LLM 소견 섹션 생성 (AI 측정 점수 18항목 순서로 정렬)
    metric_order = [
        "melasma_score",
        "freckle_score",
        "redness_score",
        "post_inflammatory_erythema_score",
        "acne_score",
        "post_acne_pigment_score",
        "pore_size_score",
        "pore_sagging_score",
        "eye_wrinkle_score",
        "nasolabial_wrinkle_score",
        "fine_deep_wrinkle_score",
        "roughness_score",
        "skin_tone_score",
        "dullness_score",
        "uneven_tone_score",
        "jawline_blur_score",
        "cheek_sagging_score",
        "skin_type_score",
    ]
    metric_opinions_section = ""
    if metric_opinions:
        for metric_name in metric_order:
            if metric_name in metric_opinions and metric_opinions[metric_name]:
                opinion = metric_opinions[metric_name]
                metric_opinions_section += f"""
                <div class="metric-item">
                    <div class="metric-name">{metric_name}</div>
                    <div class="metric-opinion">{opinion}</div>
                </div>
                """
    else:
        metric_opinions_section = "<p>항목별 AI 소견이 없습니다.</p>"
    
    # AI 피부건강지수 표시 문자열 생성
    orig_llm_overall_score_display = f"{int(round(orig_llm_overall_score))}점" if orig_llm_overall_score is not None else "-"
    ref_llm_overall_score_display = f"{int(round(ref_llm_overall_score))}점" if ref_llm_overall_score is not None else "-"
    
    # 처방전 섹션 생성 (상세 테이블에 표시되므로 여기서는 비워둠)
    prescription_section = ""
    
    # 활성 믹스 테이블 생성
    active_mixes_table = ""
    if active_mixes:
        for mix_code in sorted(active_mixes.keys()):
            if mix_code.startswith("M") and mix_code != "_note":
                mix_info = active_mixes[mix_code]
                name = mix_info.get("name", "")
                category = mix_info.get("category", "")
                description = mix_info.get("description", "")
                ingredients = ", ".join(mix_info.get("ingredients", []))
                # 처방전에서 배합비 추출
                percentage = ""
                if prescription:
                    # assessment에서 배합비 추출
                    if "assessment" in prescription:
                        assessment = prescription.get("assessment", {})
                        if mix_code in assessment:
                            mix_data = assessment[mix_code]
                            if isinstance(mix_data, dict):
                                percentage = f"{mix_data.get('percentage', 0)}%"
                            else:
                                percentage = f"{mix_data}%"
                    # M01(베이스믹스)인 경우 base 섹션에서도 배합비 추출
                    if mix_code == "M01" and "base" in prescription:
                        base_data = prescription.get("base", {})
                        if isinstance(base_data, dict):
                            percentage = f"{base_data.get('percentage', 0)}%"
                        else:
                            percentage = f"{base_data}%"
                active_mixes_table += f"""
                <tr>
                    <td>{mix_code}</td>
                    <td>{name}</td>
                    <td>{category}</td>
                    <td>{description}</td>
                    <td>{ingredients}</td>
                    <td>{percentage}</td>
                </tr>
                """
    else:
        active_mixes_table = "<tr><td colspan='6'>활성 믹스 정보가 없습니다.</td></tr>"
    
    # PCR 믹스 테이블 생성
    pcr_mixes_table = ""
    if pcr_mixes:
        for mix_code in sorted(pcr_mixes.keys()):
            if mix_code.startswith("PM") and mix_code != "_note":
                mix_info = pcr_mixes[mix_code]
                name = mix_info.get("name", "")
                category = mix_info.get("category", "")
                description = mix_info.get("description", "")
                ingredients = ", ".join(mix_info.get("ingredients", []))
                # 처방전에서 배합비 추출
                percentage = ""
                if prescription and "pcr" in prescription:
                    pcr_prescription = prescription.get("pcr", {})
                    if mix_code in pcr_prescription:
                        mix_data = pcr_prescription[mix_code]
                        if isinstance(mix_data, dict):
                            percentage = f"{mix_data.get('percentage', 0)}%"
                        else:
                            percentage = f"{mix_data}%"
                pcr_mixes_table += f"""
                <tr>
                    <td>{mix_code}</td>
                    <td>{name}</td>
                    <td>{category}</td>
                    <td>{description}</td>
                    <td>{ingredients}</td>
                    <td>{percentage}</td>
                </tr>
                """
    else:
        pcr_mixes_table = "<tr><td colspan='6'>PCR 믹스 정보가 없습니다.</td></tr>"
    
    return html_template.format(
        title=title,
        timestamp=timestamp,
        original_image_uri=original_image_uri,
        restored_image_uri=restored_image_uri,
        table_rows=table_rows,
        llm_overall_opinion=llm_overall_opinion,
        recommendation_items=recommendation_items,
        products_section=products_section,
        metric_opinions_section=metric_opinions_section,
        orig_llm_overall_score_display=orig_llm_overall_score_display,
        ref_llm_overall_score_display=ref_llm_overall_score_display,
        prescription_section=prescription_section,
        active_mixes_table=active_mixes_table,
        pcr_mixes_table=pcr_mixes_table,
    )
