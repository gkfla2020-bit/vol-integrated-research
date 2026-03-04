#!/usr/bin/env python3
"""
통합 연구 논문 HTML 생성기
vol_3_final + 차트 → 아름다운 HTML
"""

import re
import os
from datetime import datetime

# 최종본 읽기
with open("vol_3_final_20260208_231823.md", "r", encoding="utf-8") as f:
    md = f.read()

# "# Step 3: Opus 4.6 최종본" 제거
md = md.replace("# Step 3: Opus 4.6 최종본\n\n", "")

# 차트 파일 확인
charts = [f for f in os.listdir('.') if f.startswith('vol_chart_') and f.endswith('.png')]
print(f"차트 파일: {charts}")

def md_to_html(text):
    """마크다운을 HTML로 변환"""
    lines = text.split('\n')
    html_parts = []
    in_table = False
    in_code = False
    table_rows = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # 코드 블록
        if line.strip().startswith('```'):
            if in_code:
                in_code = False
                html_parts.append('</div>')
            else:
                in_code = True
                html_parts.append('<div class="math-block">')
            i += 1
            continue
        
        if in_code:
            html_parts.append(f'\\[{line}\\]' if line.strip() else '')
            i += 1
            continue
        
        # 테이블
        if '|' in line and line.strip().startswith('|'):
            cells = [c.strip() for c in line.strip().split('|')[1:-1]]
            if all(set(c) <= set('-: ') for c in cells):
                i += 1
                continue
            if not in_table:
                in_table = True
                # 이전 줄이 caption이면 사용
                caption = ''
                if html_parts and '표 ' in str(html_parts[-1]):
                    caption = html_parts.pop()
                    caption = re.sub(r'<[^>]+>', '', caption).strip()
                    caption = re.sub(r'\*\*([^*]+)\*\*', r'\1', caption)
                html_parts.append('<table>')
                if caption:
                    html_parts.append(f'<caption>{caption}</caption>')
                # 첫 행은 헤더
                html_parts.append('<thead><tr>')
                for c in cells:
                    c = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', c)
                    html_parts.append(f'<th>{c}</th>')
                html_parts.append('</tr></thead><tbody>')
                i += 1
                continue
            else:
                html_parts.append('<tr>')
                for j, c in enumerate(cells):
                    cls = ' class="left"' if j == 0 else ''
                    # 유의성 표시
                    c = re.sub(r'\*\*\*', '<span class="sig">***</span>', c)
                    c = re.sub(r'\*\*([^*])', r'<span class="sig">**</span>\1', c)
                    c = re.sub(r'\*\*$', '<span class="sig">**</span>', c)
                    c = re.sub(r'(?<!\*)\*(?!\*)', '<span class="sig">*</span>', c)
                    html_parts.append(f'<td{cls}>{c}</td>')
                html_parts.append('</tr>')
                i += 1
                continue
        elif in_table:
            in_table = False
            html_parts.append('</tbody></table>')
        
        # 헤더
        if line.startswith('## ') and not line.startswith('### '):
            if in_table:
                in_table = False
                html_parts.append('</tbody></table>')
            title = line[3:].strip()
            title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title)
            html_parts.append(f'<div class="section-divider">• • •</div>')
            html_parts.append(f'<h2>{title}</h2>')
            i += 1
            continue
        
        if line.startswith('### '):
            title = line[4:].strip()
            title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title)
            html_parts.append(f'<h3>{title}</h3>')
            i += 1
            continue
        
        if line.startswith('#### '):
            title = line[5:].strip()
            title = re.sub(r'\*\*([^*]+)\*\*', r'\1', title)
            html_parts.append(f'<h4 style="font-size:1.05em;color:#2c3e50;margin:20px 0 10px;">{title}</h4>')
            i += 1
            continue
        
        # 빈 줄
        if not line.strip():
            i += 1
            continue
        
        # 가설 박스
        if line.strip().startswith('**가설'):
            content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line.strip())
            html_parts.append(f'<div class="hypothesis">{content}</div>')
            i += 1
            continue
        
        # Finding box
        if '핵심 발견' in line or '핵심 변화' in line:
            content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', line.strip())
            html_parts.append(f'<div class="finding-box"><h4>핵심 발견</h4><p>{content}</p></div>')
            i += 1
            continue
        
        # 리스트
        if line.strip().startswith('- ') or (line.strip() and line.strip()[0].isdigit() and '. ' in line.strip()[:4]):
            content = line.strip()
            if content.startswith('- '):
                content = content[2:]
            else:
                content = re.sub(r'^\d+\.\s*', '', content)
            content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)
            html_parts.append(f'<p class="no-indent" style="margin-left:2em;">• {content}</p>')
            i += 1
            continue
        
        # 일반 단락
        content = line.strip()
        content = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', content)
        
        no_indent = content.startswith('주요 발견') or content.startswith('***') or content.startswith('핵심')
        cls = ' class="no-indent"' if no_indent else ''
        html_parts.append(f'<p{cls}>{content}</p>')
        i += 1
    
    if in_table:
        html_parts.append('</tbody></table>')
    
    return '\n'.join(html_parts)

# Abstract 분리
abstract_match = re.search(r'## Abstract\s*\n(.*?)(?=\n## )', md, re.DOTALL)
abstract_text = abstract_match.group(1).strip() if abstract_match else ""

# 본문 (Abstract 이후)
body_start = md.find('## 1.')
body_text = md[body_start:] if body_start > 0 else md

body_html = md_to_html(body_text)

# 차트 삽입 위치
chart_insertions = {
    'DCC-GARCH': ('vol_chart_rolling_corr.png', '그림 1: 주요 자산쌍의 252일 롤링 상관관계 (2000-2025)'),
    'Vasicek': ('vol_chart_vasicek.png', '그림 2: 단기금리 경로와 바시첵 장기 평균'),
    'BEI': ('vol_chart_bei_gold.png', '그림 3: 기대인플레이션과 금 가격'),
    'Spillover': ('vol_chart_spillover.png', '그림 4: VAR 전이효과 히트맵 (2014-2025)'),
    'BTC Rolling': ('vol_chart_btc_rolling.png', '그림 5: BTC 252일 롤링 상관관계'),
    'Monday': ('vol_chart_monday_effect.png', '그림 6: 주말 변동성 보정 효과'),
}

# 차트 HTML 생성
def chart_html(filename, caption):
    if os.path.exists(filename):
        return f'''<div class="chart-container">
    <img src="{filename}" alt="{caption}">
    <div class="chart-caption">{caption}</div>
</div>'''
    return ''

# 본문에 차트 삽입
for key, (fname, cap) in chart_insertions.items():
    ch = chart_html(fname, cap)
    if ch:
        if 'rolling_corr' in fname:
            body_html = body_html.replace('</h2>\n<h3>5.2', f'</h2>\n{ch}\n<h3>5.2')
        elif 'vasicek' in fname:
            body_html = body_html.replace('<h3>5.2 DCC', f'{ch}\n<h3>5.2 DCC')
        elif 'bei_gold' in fname:
            body_html = body_html.replace('<h3>5.4 구조변화', f'{ch}\n<h3>5.4 구조변화')
        elif 'spillover' in fname:
            body_html = body_html.replace('<h3>5.6 VAR', f'{ch}\n<h3>5.6 VAR')
        elif 'btc_rolling' in fname:
            body_html = body_html.replace('## 6.', f'{ch}\n<div class="section-divider">• • •</div>\n<h2>6.')
        elif 'monday' in fname:
            body_html = body_html.replace('<h3>5.4 구조변화', f'{ch}\n<h3>5.4 구조변화')


# HTML 템플릿
html = f'''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>자산 동조화와 거시적 전환점 분석 | Ha Rim Jung</title>
    <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:ital,wght@0,400;0,600;0,700;1,400&family=Inter:wght@300;400;500;600&family=Nanum+Myeongjo:wght@400;700&display=swap" rel="stylesheet">
    <script>
        window.MathJax = {{
            tex: {{ inlineMath: [['\\\\(','\\\\)']], displayMath: [['\\\\[','\\\\]']] }},
            svg: {{ fontCache: 'global' }}
        }};
    </script>
    <script src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-svg.js" async></script>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, sans-serif;
            background: #f5f5f0;
            color: #1a1a1a;
            line-height: 1.8;
        }}
        .header-bar {{
            background: linear-gradient(135deg, #0a192f 0%, #112240 40%, #1d3557 70%, #457b9d 100%);
            padding: 65px 40px 55px;
            text-align: center;
            color: white;
            position: relative;
            overflow: hidden;
        }}
        .header-bar::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background: url("data:image/svg+xml,%3Csvg width='80' height='80' viewBox='0 0 80 80' xmlns='http://www.w3.org/2000/svg'%3E%3Cg fill='none' fill-rule='evenodd'%3E%3Cg fill='%23ffffff' fill-opacity='0.03'%3E%3Cpath d='M50 50c0-5.523 4.477-10 10-10s10 4.477 10 10-4.477 10-10 10c0 5.523-4.477 10-10 10s-10-4.477-10-10 4.477-10 10-10zM10 10c0-5.523 4.477-10 10-10s10 4.477 10 10-4.477 10-10 10c0 5.523-4.477 10-10 10S0 25.523 0 20s4.477-10 10-10z'/%3E%3C/g%3E%3C/g%3E%3C/svg%3E");
            opacity: 0.5;
        }}
        .header-bar .category {{
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 3px;
            text-transform: uppercase;
            color: #e63946;
            margin-bottom: 20px;
            position: relative;
        }}
        .header-bar h1 {{
            font-family: 'Cormorant Garamond', 'Nanum Myeongjo', serif;
            font-size: 2.1em;
            font-weight: 700;
            line-height: 1.3;
            max-width: 850px;
            margin: 0 auto 15px;
            position: relative;
        }}
        .header-bar .subtitle {{
            font-family: 'Cormorant Garamond', serif;
            font-size: 1.05em;
            font-weight: 400;
            font-style: italic;
            color: rgba(255,255,255,0.7);
            max-width: 750px;
            margin: 0 auto 25px;
            position: relative;
        }}
        .header-bar .author {{
            font-size: 14px;
            font-weight: 500;
            color: rgba(255,255,255,0.85);
            position: relative;
        }}
        .header-bar .date {{
            font-size: 12px;
            color: rgba(255,255,255,0.5);
            margin-top: 5px;
            position: relative;
        }}
        .container {{
            max-width: 920px;
            margin: 0 auto;
            padding: 0 40px 80px;
        }}
        .paper-content {{
            font-family: 'Times New Roman', 'Nanum Myeongjo', serif;
            background: #fff;
            padding: 50px 55px;
            margin-top: -30px;
            border-radius: 8px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.08);
            position: relative;
            z-index: 1;
            font-size: 15px;
            line-height: 1.9;
        }}
        .abstract {{
            background: linear-gradient(135deg, #f8f9fa, #edf2f4);
            border-left: 4px solid #1d3557;
            padding: 25px 30px;
            margin: 30px 0;
            border-radius: 0 6px 6px 0;
            font-size: 13.5px;
            line-height: 1.8;
            color: #333;
        }}
        .abstract-title {{
            font-family: 'Inter', sans-serif;
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: #1d3557;
            margin-bottom: 10px;
        }}
        .keywords {{
            background: #fafafa;
            padding: 12px 20px;
            border-radius: 6px;
            font-size: 13px;
            color: #555;
            margin-bottom: 30px;
        }}
        .keywords strong {{ color: #1d3557; }}
        h2 {{
            font-family: 'Cormorant Garamond', 'Nanum Myeongjo', serif;
            font-size: 1.5em;
            font-weight: 700;
            color: #1d3557;
            margin: 40px 0 15px;
            padding-bottom: 8px;
            border-bottom: 1px solid #e0e0e0;
        }}
        h3 {{
            font-family: 'Cormorant Garamond', 'Nanum Myeongjo', serif;
            font-size: 1.2em;
            font-weight: 600;
            color: #2c3e50;
            margin: 30px 0 12px;
        }}
        p {{
            text-align: justify;
            text-indent: 2em;
            margin-bottom: 12px;
        }}
        p.no-indent {{ text-indent: 0; }}
        .hypothesis {{
            background: linear-gradient(135deg, #f8f9fa, #fff);
            border-left: 3px solid #e63946;
            padding: 15px 20px;
            margin: 12px 0;
            border-radius: 0 6px 6px 0;
        }}
        .hypothesis strong {{ color: #e63946; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 12.5px;
        }}
        table caption {{
            font-weight: 700;
            text-align: left;
            margin-bottom: 8px;
            font-size: 13.5px;
            color: #1d3557;
        }}
        thead th {{
            background: #1d3557;
            color: white;
            padding: 10px 10px;
            font-weight: 600;
            font-size: 11.5px;
            text-align: center;
            white-space: nowrap;
        }}
        tbody td {{
            padding: 7px 10px;
            border-bottom: 1px solid #eee;
            text-align: center;
        }}
        tbody tr:nth-child(even) {{ background: #fafafa; }}
        tbody tr:hover {{ background: #f0f4ff; }}
        td.left {{ text-align: left; }}
        .sig {{ color: #e63946; font-weight: 700; }}
        .note {{
            font-size: 11.5px;
            color: #777;
            margin-top: 5px;
            font-style: italic;
        }}
        .chart-container {{
            margin: 25px 0;
            text-align: center;
        }}
        .chart-container img {{
            max-width: 100%;
            border-radius: 6px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .chart-caption {{
            font-size: 12px;
            color: #666;
            margin-top: 8px;
            font-style: italic;
        }}
        .finding-box {{
            background: linear-gradient(135deg, #0a192f, #1d3557);
            color: white;
            padding: 25px 30px;
            border-radius: 8px;
            margin: 25px 0;
        }}
        .finding-box h4 {{
            color: #e63946;
            font-family: 'Inter', sans-serif;
            font-size: 12px;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 12px;
        }}
        .finding-box p {{ text-indent: 0; color: rgba(255,255,255,0.9); }}
        .references {{
            font-size: 12.5px;
            line-height: 1.7;
        }}
        .references p {{
            text-indent: -2em;
            padding-left: 2em;
            margin-bottom: 6px;
        }}
        .math-block {{
            margin: 15px 0;
            padding: 10px 0;
            text-align: center;
            overflow-x: auto;
        }}
        .section-divider {{
            text-align: center;
            margin: 40px 0;
            color: #ccc;
            font-size: 18px;
            letter-spacing: 10px;
        }}
        .vasicek-highlight {{
            background: linear-gradient(135deg, #457b9d15, #1d355710);
            border: 1px solid #457b9d40;
            border-radius: 8px;
            padding: 20px 25px;
            margin: 20px 0;
        }}
        .vasicek-highlight h4 {{
            color: #1d3557;
            font-family: 'Inter', sans-serif;
            font-size: 13px;
            font-weight: 600;
            margin-bottom: 10px;
        }}
        @media (max-width: 768px) {{
            .header-bar {{ padding: 40px 20px 35px; }}
            .header-bar h1 {{ font-size: 1.5em; }}
            .container {{ padding: 0 15px 40px; }}
            .paper-content {{ padding: 25px 20px; font-size: 14px; }}
            table {{ font-size: 11px; }}
            thead th, tbody td {{ padding: 6px 4px; }}
        }}
    </style>
</head>
<body>

<div class="header-bar">
    <div class="category">Working Paper &middot; February 2026</div>
    <h1>자산 동조화와 거시적 전환점</h1>
    <div class="subtitle">바시첵 모델과 주말 보정 DCC-GARCH를 활용한 채권-원자재-비트코인 통합 분석 (1995-2025)</div>
    <div class="author">Ha Rim Jung</div>
    <div class="date">Asset Co-movement and Macroeconomic Turning Points: An Integrated Analysis of Bonds, Commodities, and Bitcoin Using Vasicek Model and Weekend-Adjusted DCC-GARCH</div>
</div>

<div class="container">
<div class="paper-content">

<div class="abstract">
    <div class="abstract-title">Abstract</div>
    {abstract_text}
</div>

<div class="keywords">
    <strong>Keywords:</strong> Asset Co-movement, Vasicek Model, DCC-GARCH, Weekend Volatility Adjustment, Structural Break, Bitcoin Financialization, Spillover Index, Mean Reversion, Breakeven Inflation, Monetary Policy Regime
</div>

{body_html}

</div>
</div>

</body>
</html>'''

# 저장
with open('vol_research_paper.html', 'w', encoding='utf-8') as f:
    f.write(html)

print(f"✓ vol_research_paper.html 생성 완료 ({len(html):,} bytes)")
