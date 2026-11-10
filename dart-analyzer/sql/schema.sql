-- DART 데이터 마트 (SQLite). 원천 → 정규화 테이블 → 분석용 뷰
CREATE TABLE IF NOT EXISTS companies (
  corp_code   TEXT PRIMARY KEY,
  corp_name   TEXT NOT NULL,
  stock_code  TEXT,
  sector      TEXT              -- 내 관심 분류 (config 의 그룹)
);

CREATE TABLE IF NOT EXISTS filings (
  rcept_no    TEXT PRIMARY KEY,
  corp_code   TEXT NOT NULL REFERENCES companies(corp_code),
  report_nm   TEXT NOT NULL,
  rcept_dt    TEXT NOT NULL      -- YYYYMMDD
);

CREATE TABLE IF NOT EXISTS financials (
  corp_code   TEXT NOT NULL REFERENCES companies(corp_code),
  bsns_year   INTEGER NOT NULL,
  account     TEXT NOT NULL,     -- revenue · operating_income · net_income · total_assets · total_liabilities · total_equity
  fs_div      TEXT,              -- CFS 연결 / OFS 별도
  amount      INTEGER,
  prev_amount INTEGER,
  rcept_no    TEXT,
  PRIMARY KEY (corp_code, bsns_year, account)
);

CREATE TABLE IF NOT EXISTS paragraphs (
  rcept_no    TEXT NOT NULL REFERENCES filings(rcept_no),
  para_no     INTEGER NOT NULL,
  section     TEXT,
  text        TEXT NOT NULL,
  PRIMARY KEY (rcept_no, para_no)
);

-- 연도별 핵심 지표: 계정을 열로 펼치고(피벗) 비율 계산
DROP VIEW IF EXISTS v_metrics;
CREATE VIEW v_metrics AS
SELECT c.corp_name, c.sector, f.corp_code, f.bsns_year,
       MAX(CASE WHEN account = 'revenue'           THEN amount END) AS revenue,
       MAX(CASE WHEN account = 'operating_income'  THEN amount END) AS operating_income,
       MAX(CASE WHEN account = 'net_income'        THEN amount END) AS net_income,
       MAX(CASE WHEN account = 'total_liabilities' THEN amount END) AS liabilities,
       MAX(CASE WHEN account = 'total_equity'      THEN amount END) AS equity,
       ROUND(100.0 * MAX(CASE WHEN account = 'operating_income' THEN amount END)
                   / NULLIF(MAX(CASE WHEN account = 'revenue' THEN amount END), 0), 2) AS op_margin_pct,
       ROUND(100.0 * MAX(CASE WHEN account = 'total_liabilities' THEN amount END)
                   / NULLIF(MAX(CASE WHEN account = 'total_equity' THEN amount END), 0), 1) AS debt_ratio_pct
FROM financials f JOIN companies c USING (corp_code)
GROUP BY f.corp_code, f.bsns_year;

-- 전년 대비 증가율: 윈도 함수 LAG
DROP VIEW IF EXISTS v_growth;
CREATE VIEW v_growth AS
SELECT corp_name, sector, bsns_year, revenue, operating_income, op_margin_pct,
       ROUND(100.0 * (revenue - LAG(revenue) OVER w) / NULLIF(ABS(LAG(revenue) OVER w), 0), 2) AS revenue_yoy_pct,
       ROUND(100.0 * (operating_income - LAG(operating_income) OVER w) / NULLIF(ABS(LAG(operating_income) OVER w), 0), 2) AS op_income_yoy_pct
FROM v_metrics
WINDOW w AS (PARTITION BY corp_code ORDER BY bsns_year);

-- 같은 분류 안에서 영업이익률 순위
DROP VIEW IF EXISTS v_sector_rank;
CREATE VIEW v_sector_rank AS
SELECT sector, bsns_year, corp_name, op_margin_pct,
       RANK() OVER (PARTITION BY sector, bsns_year ORDER BY op_margin_pct DESC) AS margin_rank
FROM v_metrics
WHERE op_margin_pct IS NOT NULL;
