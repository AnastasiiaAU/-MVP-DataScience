from datetime import datetime, timezone

import pytest

from db import crud


@pytest.mark.asyncio
async def test_add_user_creates_user(db_session):
    user = await crud.add_user(db_session, telegram_id=123456789, username="alice")

    assert user.id is not None
    assert user.telegram_id == 123456789
    assert user.username == "alice"


@pytest.mark.asyncio
async def test_add_user_duplicate_returns_existing(db_session):
    first = await crud.add_user(db_session, telegram_id=777, username="first")
    second = await crud.add_user(db_session, telegram_id=777, username="second")

    assert second.id == first.id
    assert second.username == "second"


@pytest.mark.asyncio
async def test_add_article_success(db_session):
    source = await crud.add_source(db_session, "@source_one")
    article = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=10,
        text="A" * 120,
        url="https://t.me/source_one/10",
        published_at=datetime.now(timezone.utc),
    )

    assert article is not None
    assert article.source_id == source.id
    assert article.telegram_message_id == 10
    assert len(article.hash) == 64


@pytest.mark.asyncio
async def test_add_article_duplicate_hash_returns_none(db_session):
    source = await crud.add_source(db_session, "@source_dup")
    text = "same content for deduplication" * 4

    first = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=1,
        text=text,
        url="https://t.me/source_dup/1",
        published_at=datetime.now(timezone.utc),
    )
    second = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=2,
        text=text,
        url="https://t.me/source_dup/2",
        published_at=datetime.now(timezone.utc),
    )

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_get_unprocessed_articles_filters_processed(db_session):
    source = await crud.add_source(db_session, "@source_filter")
    article_1 = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=100,
        text="text 100" * 20,
        url="https://t.me/source_filter/100",
        published_at=datetime.now(timezone.utc),
    )
    article_2 = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=101,
        text="text 101" * 20,
        url="https://t.me/source_filter/101",
        published_at=datetime.now(timezone.utc),
    )

    await crud.mark_article_processed(db_session, article_1.id)

    unprocessed = await crud.get_unprocessed_articles(db_session, limit=50)
    ids = {article.id for article in unprocessed}

    assert article_1.id not in ids
    assert article_2.id in ids


@pytest.mark.asyncio
async def test_save_summary_and_risk_assessment_chain(db_session):
    source = await crud.add_source(db_session, "@chain_source")
    article = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=50,
        text="transport and tariffs" * 30,
        url="https://t.me/chain_source/50",
        published_at=datetime.now(timezone.utc),
    )

    summary = await crud.save_summary(
        db_session,
        article_id=article.id,
        summary_text="Рост тарифов затрагивает перевозчиков.",
        industries=["Логистика"],
        regions=["ЦФО"],
        event_type="economic",
        tokens=150,
    )
    risk = await crud.save_risk_assessment(
        db_session,
        summary_id=summary.id,
        risk_level="high",
        confidence=0.82,
        okveds=["49.41"],
        explanation="Существенное влияние на себестоимость перевозок.",
    )

    assert summary.article_id == article.id
    assert risk.summary_id == summary.id
    assert risk.risk_level == "high"
    assert risk.okved_codes == ["49.41"]


@pytest.mark.asyncio
async def test_get_user_risks_returns_joined_data(db_session):
    user = await crud.add_user(db_session, telegram_id=9001, username="risk_user")
    source = await crud.add_source(db_session, "@joined_source")
    article = await crud.add_article(
        db_session,
        source_id=source.id,
        message_id=777,
        text="important business update" * 25,
        url="https://t.me/joined_source/777",
        published_at=datetime.now(timezone.utc),
    )

    summary = await crud.save_summary(
        db_session,
        article_id=article.id,
        summary_text="Событие может повлиять на бизнес в регионе.",
        industries=["Торговля"],
        regions=["ЦФО"],
        event_type="economic",
        tokens=120,
    )
    risk = await crud.save_risk_assessment(
        db_session,
        summary_id=summary.id,
        risk_level="medium",
        confidence=0.66,
        okveds=["47"],
        explanation="Умеренное влияние на розничный сектор.",
    )
    await crud.save_notification(db_session, user_id=user.id, risk_assessment_id=risk.id)

    results = await crud.get_user_risks(db_session, telegram_id=9001, limit=10)

    assert len(results) == 1
    assert results[0].id == risk.id
    assert results[0].summary.article.id == article.id


@pytest.mark.asyncio
async def test_get_users_for_notification_filters_by_okved_and_threshold(db_session):
    user_1 = await crud.add_user(db_session, telegram_id=1001, username="u1")
    await crud.update_user_settings(db_session, user_1.telegram_id, ["49"], ["ЦФО"], "medium")

    user_2 = await crud.add_user(db_session, telegram_id=1002, username="u2")
    await crud.update_user_settings(db_session, user_2.telegram_id, ["10"], ["ЦФО"], "low")

    user_3 = await crud.add_user(db_session, telegram_id=1003, username="u3")
    await crud.update_user_settings(db_session, user_3.telegram_id, ["49"], ["СФО"], "low")

    user_4 = await crud.add_user(db_session, telegram_id=1004, username="u4")
    await crud.update_user_settings(db_session, user_4.telegram_id, [], [], "high")

    user_5 = await crud.add_user(db_session, telegram_id=1005, username="u5")
    await crud.update_user_settings(db_session, user_5.telegram_id, [], [], "low")

    matched = await crud.get_users_for_notification(
        db_session,
        okved_codes=["49"],
        regions=["ЦФО"],
        min_risk_level="medium",
    )

    matched_ids = {user.telegram_id for user in matched}
    assert matched_ids == {1001, 1005}
