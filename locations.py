"""등록용 행정 읍·면·동 목록. 행정구역 변경 시 갱신해야 하는 로컬 데이터.

참고 자료 (2026-10-19 조회):
거제: https://www.geoje.go.kr/stat/index.geoje?menuCd=DOM_000008905001007000
고성: https://www.goseong.go.kr/uploadFile/pdf/gunjung_2017.pdf
남해: https://www.namhae.go.kr/portal/Index.do?c=WW0601000000
사천: https://www.sacheon.go.kr/portal/data/hwp/minwon/2021/03635_2021_08.pdf
진해: https://www.changwon.go.kr/cwportal/_res/cwportal/data/pdf/minwon202606.pdf
통영: https://www.codil.or.kr/filebank/original/RK/OTKCRK240603/OTKCRK240603.pdf
하동: https://www.hadong.go.kr/intro/00668.web
"""

DISTRICTS = {
    "거제시": "일운면 동부면 남부면 거제면 둔덕면 사등면 연초면 하청면 장목면 장승포동 능포동 아주동 옥포1동 옥포2동 장평동 고현동 상문동 수양동".split(),
    "고성군": "고성읍 삼산면 하일면 하이면 상리면 대가면 영현면 영오면 개천면 구만면 회화면 마암면 동해면 거류면".split(),
    "남해군": "남해읍 이동면 상주면 삼동면 미조면 남면 서면 고현면 설천면 창선면".split(),
    "사천시": "사천읍 정동면 사남면 용현면 축동면 곤양면 곤명면 서포면 동서동 선구동 동서금동 벌용동 향촌동 남양동".split(),
    "창원시(진해구)": "충무동 여좌동 태백동 경화동 병암동 석동 이동 자은동 덕산동 풍호동 웅천동 웅동1동 웅동2동".split(),
    "통영시": "산양읍 용남면 도산면 광도면 욕지면 한산면 사량면 도천동 명정동 중앙동 정량동 북신동 무전동 미수동 봉평동".split(),
    "하동군": "하동읍 화개면 악양면 적량면 횡천면 고전면 금남면 금성면 진교면 양보면 북천면 청암면 옥종면".split(),
}
