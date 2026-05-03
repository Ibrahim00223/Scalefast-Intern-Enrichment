from rapidfuzz import fuzz
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.lead import Lead
from app.schemas.lead import LeadOut
from app.schemas.lookup import LookupResult
from app.services.normalization import normalize_linkedin_url, normalize_name


async def lookup_lead(
    first_name: str,
    last_name: str,
    linkedin_url: str | None,
    session: AsyncSession,
) -> LookupResult:
    # Pass 1: LinkedIn exact match
    normalized_linkedin = normalize_linkedin_url(linkedin_url)
    if normalized_linkedin:
        stmt = select(Lead).where(Lead.linkedin_url == normalized_linkedin)
        result = await session.execute(stmt)
        lead = result.scalar_one_or_none()
        if lead:
            return LookupResult(
                found=True,
                score=1.0,
                match_type="linkedin_exact",
                lead=LeadOut.model_validate(lead),
            )

    # Pass 2: Fuzzy first_name + last_name via pg_trgm blocking + rapidfuzz scoring
    first_n = normalize_name(first_name)
    last_n = normalize_name(last_name)
    threshold = settings.LOOKUP_FUZZY_THRESHOLD

    stmt = (
        select(
            Lead,
            func.similarity(Lead.last_name_normalized, last_n).label("last_sim"),
            func.similarity(Lead.first_name_normalized, first_n).label("first_sim"),
        )
        .where(
            func.similarity(Lead.last_name_normalized, last_n) > threshold,
            func.similarity(Lead.first_name_normalized, first_n) > threshold,
        )
        .order_by(
            (
                func.similarity(Lead.last_name_normalized, last_n)
                + func.similarity(Lead.first_name_normalized, first_n)
            ).desc()
        )
        .limit(5)
    )

    result = await session.execute(stmt)
    candidates = result.all()

    if not candidates:
        return LookupResult(found=False, score=0.0, match_type=None, lead=None)

    best_lead, best_score = None, 0.0
    for row in candidates:
        lead = row[0]
        last_score = fuzz.token_sort_ratio(last_n, lead.last_name_normalized) / 100
        first_score = fuzz.token_sort_ratio(first_n, lead.first_name_normalized) / 100
        score = last_score * 0.5 + first_score * 0.5
        if score > best_score:
            best_score, best_lead = score, lead

    if best_lead is None or best_score < threshold:
        return LookupResult(found=False, score=0.0, match_type=None, lead=None)

    return LookupResult(
        found=True,
        score=round(best_score, 4),
        match_type="name_fuzzy",
        lead=LeadOut.model_validate(best_lead),
    )
