"""어떤 나라·어떤 열을 받을지 — 수집과 분석이 같은 목록을 씁니다."""

# 표시 이름 → (Ember 이름, OWID 이름). 한국과 비교할 나라: 이웃(일본·중국·대만), 전환이 빠른 나라(영국·독일·스페인),
# 원자력 비중이 큰 나라(프랑스), 자원 수출국(호주·미국), 수요가 빠르게 느는 나라(인도), 세계 평균
COUNTRIES = {
    "한국": ("South Korea", "South Korea"),
    "일본": ("Japan", "Japan"),
    "중국": ("China", "China"),
    "대만": ("Taiwan (China)", "Taiwan"),
    "독일": ("Germany", "Germany"),
    "영국": ("United Kingdom", "United Kingdom"),
    "스페인": ("Spain", "Spain"),
    "프랑스": ("France", "France"),
    "미국": ("United States", "United States"),
    "호주": ("Australia", "Australia"),
    "인도": ("India", "India"),
    "세계": ("World", "World"),
}

EMBER_FROM = "2015-01-01"   # 월별 자료는 이 달부터 (한국 태양광이 1%를 넘기 전부터 보이도록)
EMBER_URL = "https://files.ember-energy.org/public-downloads/generation/outputs/release_generation_monthly_global.csv"
OWID_URL = "https://raw.githubusercontent.com/owid/energy-data/master/owid-energy-data.csv"

# Ember 월별 자료에서 쓰는 열 (원본 열 이름 → 저장 이름)
EMBER_COLS = {
    "Area": "area", "Date": "month", "Electricity source": "source",
    "Generation (TWh)": "generation_twh", "Share of generation (%)": "share_pct",
    "Emissions intensity (gCO2e/kWh)": "intensity_g_per_kwh",
}
# 묶음이 아닌 개별 발전원 + 합계 (Fossil·Renewables 같은 묶음 행은 겹쳐 세지 않도록 버림)
EMBER_SOURCES = {"Coal", "Gas", "Other fossil", "Nuclear", "Hydro", "Bioenergy", "Other renewables", "Wind", "Solar", "Total generation"}

OWID_COLS = [
    "country", "year", "population", "electricity_generation", "per_capita_electricity", "carbon_intensity_elec",
    "coal_share_elec", "gas_share_elec", "oil_share_elec", "nuclear_share_elec", "hydro_share_elec",
    "wind_share_elec", "solar_share_elec", "biofuel_share_elec", "other_renewables_share_elec_exc_biofuel",
    "low_carbon_share_elec", "renewables_share_elec", "fossil_share_elec",
]
OWID_FROM_YEAR = 1990

# 화면에서 쓰는 6개 묶음 — 한국 기준으로 1% 안팎인 수력·바이오·석유·기타는 '기타'로 합침
GROUPS = ["석탄", "원자력", "가스", "기타", "풍력", "태양광"]
EMBER_GROUP = {"Coal": "석탄", "Nuclear": "원자력", "Gas": "가스", "Other fossil": "기타", "Hydro": "기타",
               "Bioenergy": "기타", "Other renewables": "기타", "Wind": "풍력", "Solar": "태양광"}
