from rapidfuzz import fuzz
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.contact import Contact
from app.schemas.lookup import LookupResult
from app.services.normalization import normalize_linkedin_url, normalize_name


async def lookup_contact(
    nom: str,
    prenom: str,
    linkedin_url: str | None,
    session: AsyncSession,
) -> LookupResult:
    # Pass 1: LinkedIn exact match
    normalized_linkedin = normalize_linkedin_url(linkedin_url)
    if normalized_linkedin:
        stmt = select(Contact).where(Contact.linkedin_url == normalized_linkedin)
        result = await session.execute(stmt)
        contact = result.scalar_one_or_none()
        if contact:
            from app.schemas.contact import ContactOut
            return LookupResult(
                found=True,
                score=1.0,
                match_type="linkedin_exact",
                contact=ContactOut.model_validate(contact),
            )

    # Pass 2: Fuzzy name match via pg_trgm blocking + rapidfuzz scoring
    nom_n = normalize_name(nom)
    prenom_n = normalize_name(prenom)

    threshold = settings.LOOKUP_FUZZY_THRESHOLD

    stmt = (
        select(
            Contact,
            func.similarity(Contact.nom_normalized, nom_n).label("nom_sim"),
            func.similarity(Contact.prenom_normalized, prenom_n).label("prenom_sim"),
        )
        .where(
            func.similarity(Contact.nom_normalized, nom_n) > threshold,
            func.similarity(Contact.prenom_normalized, prenom_n) > threshold,
        )
        .order_by(
            (
                func.similarity(Contact.nom_normalized, nom_n)
                + func.similarity(Contact.prenom_normalized, prenom_n)
            ).desc()
        )
        .limit(5)
    )

    result = await session.execute(stmt)
    candidates = result.all()

    if not candidates:
        return LookupResult(found=False, score=0.0, match_type=None, contact=None)

    best_contact = None
    best_score = 0.0

    for row in candidates:
        contact = row[0]
        nom_score = fuzz.token_sort_ratio(nom_n, contact.nom_normalized) / 100
        prenom_score = fuzz.token_sort_ratio(prenom_n, contact.prenom_normalized) / 100
        score = nom_score * 0.5 + prenom_score * 0.5
        if score > best_score:
            best_score = score
            best_contact = contact

    if best_contact is None or best_score < threshold:
        return LookupResult(found=False, score=0.0, match_type=None, contact=None)

    from app.schemas.contact import ContactOut
    return LookupResult(
        found=True,
        score=round(best_score, 4),
        match_type="name_fuzzy",
        contact=ContactOut.model_validate(best_contact),
    )
