"""Observation filters fixed before the v3 collection; never optimized on returns."""
import math
import re
from html.parser import HTMLParser

MIN_MEDIAN_TURNOVER = 1_000_000_000
MIN_SIGNAL_TURNOVER = 3_000_000_000
KIND_URL = 'https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13'
TYPE_LABELS = {'ordinary':'일반주 후보','spac':'스팩','preferred':'우선주 추정','other':'리츠·기타','unknown':'유형 미확인'}

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.rows=[]; self.row=[]; self.cell=None
    def handle_starttag(self, tag, attrs):
        if tag == 'tr': self.row=[]
        if tag in ('td','th'): self.cell=[]
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(''.join(self.cell).strip()); self.cell=None
        if tag == 'tr' and self.row: self.rows.append(self.row)

def parse_kind(text):
    parser=TableParser(); parser.feed(text)
    if not parser.rows or parser.rows[0][:3] != ['회사명','시장구분','종목코드']:
        raise ValueError('KIND 목록 형식 변경')
    result={}
    for row in parser.rows[1:]:
        if len(row)<5 or row[1] not in ('유가','코스닥'): continue
        code=row[2]
        if not re.fullmatch(r'[0-9A-Z]{6}',code) or code in result:
            raise ValueError('KIND 코드 중복 또는 형식 오류')
        result[code]={'name':row[0],'market':'KOSPI' if row[1]=='유가' else 'KOSDAQ','industry':row[3]}
    return result

def normalize(name):
    return re.sub(r'[\s()㈜·.]','',name.replace('주식회사','')).casefold()

def classify(info, listed):
    """Require a primary-code/name match; a name alone never grants default entry."""
    name, code=info['name'],info['ticker']
    official=listed.get(code)
    kind='unknown'; reason='KRX 대표코드·명칭 대조 불가'; confidence='미확인'
    if official and official['market']==info['market'] and normalize(name)==normalize(official['name']):
        if re.search(r'스팩|기업인수목적|SPAC',name,re.I): kind='spac'
        elif re.search(r'리츠|부동산투자|인프라|맥쿼리|선박투자',name): kind='other'
        else: kind='ordinary'
        reason='KIND 대표코드·시장·명칭 일치; 명칭으로 스팩·리츠 구분'
        confidence='대표코드 대조'
    elif not official:
        base=re.sub(r'\d*우[A-Z]?(?:\(전환\))?$','',name)
        matches=[v for k,v in listed.items() if k[:5]==code[:5] and v['market']==info['market'] and normalize(v['name'])==normalize(base)]
        if base!=name and len(matches)==1:
            kind='preferred';confidence='명칭 기반 추정'
            reason='우선주 접미사 및 KIND 기초회사 코드 앞 5자리·명칭 대조; 공식 주식종류 확인 전'
    return {'stock_type':kind,'type_label':TYPE_LABELS[kind],'type_confidence':confidence,'type_reason':reason}

def liquidity_pass(row):
    values=[row.get('turnover_estimate'),row.get('median_turnover20')]
    if any(x is None or not math.isfinite(float(x)) for x in values): return False
    return values[0]>=MIN_SIGNAL_TURNOVER and values[1]>=MIN_MEDIAN_TURNOVER

def eligible(row):
    return (row.get('stock_type')=='ordinary' and liquidity_pass(row)
            and (row.get('current_volume') or 0)>0
            and not row.get('price_revision_detected',False) and row.get('score_breakdown') is not None)

def ranked_unique(rows):
    result={}
    for row in sorted(rows,key=lambda r:(r['score'],r['signal_date'],r['ticker']),reverse=True):
        result.setdefault(row['ticker'],row)
    return list(result.values())
