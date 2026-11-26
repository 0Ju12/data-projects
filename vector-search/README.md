# VectorLab — 한국어 근거 검색과 IVF 벤치마크

Python과 NumPy로 구현한 로컬 코사인 벡터 검색엔진입니다. 문서 ID·본문·정규화한 벡터·군집 번호와 중심점을 SQLite에 저장합니다. 같은 데이터에서 정확 검색과 IVF(inverted file index)를 비교할 수 있습니다. Python 3.10 이상, 엔진 코드 MIT.

## 실행

저장소를 복제한 뒤 다음 명령을 실행합니다.

```sh
cd vector-search
python -m pip install .
vectorlab build demo.sqlite vectorlab/data/documents.json --clusters 3
vectorlab search demo.sqlite '숭례문의 화재와 복구' -k 3
vectorlab search demo.sqlite '숭례문의 화재와 복구' -k 3 --probes 1
OPENBLAS_NUM_THREADS=1 vectorlab pipeline --out report.json
```

새 문서는 같은 JSON 배열 형식으로 만들어 `vectorlab add demo.sqlite new.json`으로 추가합니다. 중복 ID가 있으면 트랜잭션 전체가 취소됩니다. 기존 DB에 build를 실행하면 오류를 반환합니다. Python에서 열어 둔 Index는 읽기 시점의 스냅샷입니다. 추가한 내용을 보려면 다시 여세요.

## 직접 만든 벡터 사용

```python
from vectorlab import Index, append, save_new

save_new("custom.sqlite", ["a", "b"], ["서울", "부산"], [[1, 0], [0, 1]], clusters=2, encoder="my-model-v1")
append("custom.sqlite", ["c"], ["수원"], [[0.9, 0.1]], encoder="my-model-v1")
index = Index("custom.sqlite")
print(index.search([0.9, 0.2], k=2))
```

문서와 질문에 동일한 모델·차원을 사용합니다. 기본 CLI는 한글을 포함한 단어의 문자 2~3그램을 고정 해시 벡터로 변환합니다. 이 방식은 모델 다운로드 없이 실행되고 어휘가 바뀐 질문에서 의미를 놓칠 수 있습니다.

## 파이프라인

1. 공개 질문과 예제 문서로 인덱스를 만든 뒤 디스크에서 다시 열고 질문별 상위 3개 ID와 첫 근거 순위를 기록합니다.
2. 시드로 합성 문서 벡터와 별도 질의 벡터를 생성합니다. 군집 구조가 있는 96차원 데이터이며 문서 수 기본값은 1천·1만입니다. `--sizes 1000 5000 20000 --seed 42`로 바꿀 수 있습니다.
3. 최대 4096개 학습 표본(군집 수가 더 많으면 군집 수만큼)으로 구면 k-means 중심점을 구하고 전체 문서를 군집에 배정합니다. 추가 문서는 기존 중심점에 배정됩니다. 데이터 분포가 바뀌면 새 DB 경로에 재학습할 수 있습니다.
4. 정확 검색은 전체 문서, IVF는 질의와 가까운 군집만 점수화합니다. 동점은 ID 순서로 처리합니다. 질의마다 정확 검색 상위 10개와 비교해 Recall@10을 계산하고, 준비 실행 후 128개 질의의 p50·p95 지연을 측정합니다. DB 열기와 텍스트 인코딩 시간은 검색 지연에서 제외합니다.
5. 빌드 시간, DB 파일 크기, 상주 NumPy 배열 바이트 합, 실행 환경, 평가 데이터 해시를 JSON에 기록합니다. 배열 바이트 합은 Python 객체와 임시 버퍼를 제외합니다. GitHub Actions는 변경 시 테스트와 전체 파이프라인을 실행하고 결과를 vectorlab-report 아티팩트로 보관합니다.

## 측정 예시

[실행 결과 원본](results/reference.json). 같은 합성 벡터 1만 개, 32개 군집, 질의 128개, 단일 BLAS 스레드에서의 한 번의 측정입니다.

| 검색 | Recall@10 | p95 검색 지연 |
|---|---:|---:|
| 정확 검색 | 100% | 2.593 ms |
| IVF 1개 군집 | 96.41% | 0.105 ms |
| IVF 4개 군집 | 99.84% | 0.248 ms |
| IVF 32개 군집 | 100% | 1.620 ms |

센터와 문서 분포, 질의 차원, 장비에 따라 달라집니다. 동일 시드는 입력을 재현하며 실행 시간은 매번 변합니다.

## 한국어 근거 평가와 실패 사례

[포트폴리오의 공개 질문 9개](https://github.com/0Ju12/0Ju12.github.io/blob/4b7c1fb86e6d12b561bec00664518f5bba35da87/content/evaluation/goldset.json)를 고정했습니다. 이 예제를 위해 짧은 문서 12개와 정답 문서 ID를 직접 작성했습니다. 원본 국보 가이드 전체 문서에 대한 평가로 일반화할 수 없습니다. 답이 있는 6개에서 정확 검색과 IVF 1개 군집 모두 Hit@3와 MRR@3가 1.0이었습니다. 근거가 없는 3개는 반환 결과만 남기며 적중률 분모에서 제외합니다. 검색 점수로 답변 가능 여부를 판정하지 않습니다.

같은 질문을 다르게 표현하면 결과가 바뀝니다. 아래 질문의 근거는 gate-fire이지만 정확 검색 상위 3개에는 book-content, dabo-site, grotto-site가 나왔습니다. 전체 벡터를 비교해도 문자 겹침이 적은 표현을 놓치는 사례입니다.

```sh
vectorlab search demo.sqlite '불타버린 옛 도성 출입구를 시민들에게 다시 개방한 해는?' -k 3
```

테스트는 `python -m pip install pytest` 후 `python -m pytest -q`로 실행합니다.
