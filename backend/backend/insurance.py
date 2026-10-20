"""보험 상품 조회 API (insurance 스키마).

insurance_products 1건에 coverages·exclusions·claim_rules가 product_id로 연결됩니다.
앱의 양식 품종(예: '조피볼락 (우럭)')과 양식 방식(가두리/육상)으로 상품을 찾습니다.
"""
import re
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel

from backend.routes import DB

router = APIRouter(prefix="/api/v1/insurance", tags=["보험"])
Method = Literal["가두리", "육상"]


class InsuranceProductSummary(BaseModel):
    product_id: int
    product_name: str | None
    species: str | None
    insurance_period: str | None
    government_subsidy: str | None
    updated_at: datetime | None


class InsuranceCoverage(BaseModel):
    coverage_id: int
    coverage_key: str | None
    contract_type: str | None
    name: str | None
    risk_types: Any
    effect: str | None
    coverage_form: str | None
    is_optional: bool | None
    conditions: Any


class InsuranceExclusion(BaseModel):
    id: int
    coverage_id: int | None
    summary: str | None
    scope: str | None
    conditions: Any


class InsuranceClaimRule(BaseModel):
    id: int
    coverage_id: int | None
    rule_type: str | None
    description: str | None
    conditions: Any


class InsuranceProductDetail(BaseModel):
    product_id: int
    product_key: str | None
    product_name: str | None
    species: str | None
    document_version: str | None
    sale_period: str | None
    insurance_period: str | None
    eligibility: str | None
    government_subsidy: str | None
    deductible: str | None
    premium_payment_method: str | None
    contacts: str | None
    withdrawal_cancellation: str | None
    refund_terms: str | None
    source_files: Any
    warnings: Any
    updated_at: datetime | None
    coverages: list[InsuranceCoverage]
    exclusions: list[InsuranceExclusion]
    claim_rules: list[InsuranceClaimRule]


def species_terms(species: str) -> list[str]:
    """'조피볼락 (우럭)' → ['조피볼락', '우럭']: 괄호 밖 이름과 괄호 안 별칭 모두로 찾는다."""
    terms = [species.split("(")[0], *re.findall(r"\(([^)]*)\)", species)]
    return [t.strip() for t in terms if t.strip()]


def escape_like(term: str) -> str:
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/products", response_model=list[InsuranceProductSummary])
def products(
    db: DB,
    species: Annotated[str | None, Query(max_length=50)] = None,
    method: Method | None = None,
):
    params: list[Any] = []
    where = ""
    if species:
        terms = species_terms(species)
        if not terms:
            raise HTTPException(422, "품종 이름을 확인하세요.")
        if terms == ["기타"]:
            # '기타'는 품종이 아니라서 '수하식시설(…기타)' 같은 시설물 보험이 잘못 걸린다.
            return []
        # 품종은 species 칸이나 상품명 어느 쪽에 적혀 있어도 찾는다 (예: '굴', '조피볼락, 참돔 …').
        where = " WHERE " + " OR ".join(
            ["species ILIKE %s OR product_name ILIKE %s"] * len(terms))
        for term in terms:
            pattern = f"%{escape_like(term)}%"
            params += [pattern, pattern]
    # 양식물(수산물) 보험을 앞에, 시설물·종자 보험은 뒤에. 그다음 양식 방식이 맞는 상품을 앞에:
    # 육상이면 '육상' 상품, 가두리면 '육상'이 아닌 상품.
    order = "(product_name ILIKE '%%시설물%%' OR product_name ILIKE '%%종자%%') ASC, "
    if method == "육상":
        order += "(product_name ILIKE '%%육상%%') DESC, "
    elif method == "가두리":
        order += "(product_name ILIKE '%%육상%%') ASC, (product_name ILIKE '%%가두리%%') DESC, "
    order += "product_id"
    return db.execute(
        "SELECT product_id, product_name, species, insurance_period, government_subsidy, updated_at"
        " FROM insurance.insurance_products" + where + " ORDER BY " + order + " LIMIT 50",
        params,
    ).fetchall()


@router.get("/products/{product_id}", response_model=InsuranceProductDetail)
def product_detail(product_id: Annotated[int, Path(gt=0)], db: DB):
    product = db.execute("""
        SELECT product_id, product_key, product_name, species, document_version, sale_period,
               insurance_period, eligibility, government_subsidy, deductible, premium_payment_method,
               contacts, withdrawal_cancellation, refund_terms, source_files, warnings, updated_at
        FROM insurance.insurance_products WHERE product_id = %s
    """, (product_id,)).fetchone()
    if product is None:
        raise HTTPException(404, "해당 보험 상품이 없습니다.")
    product["coverages"] = db.execute("""
        SELECT coverage_id, coverage_key, contract_type, name, risk_types, effect,
               coverage_form, is_optional, conditions
        FROM insurance.insurance_coverages WHERE product_id = %s ORDER BY coverage_id
    """, (product_id,)).fetchall()
    product["exclusions"] = db.execute("""
        SELECT id, coverage_id, summary, scope, conditions
        FROM insurance.insurance_exclusions WHERE product_id = %s ORDER BY id
    """, (product_id,)).fetchall()
    product["claim_rules"] = db.execute("""
        SELECT id, coverage_id, rule_type, description, conditions
        FROM insurance.insurance_claim_rules WHERE product_id = %s ORDER BY id
    """, (product_id,)).fetchall()
    return product
