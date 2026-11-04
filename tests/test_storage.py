"""The persistent cache."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.briefly.storage import BrieflyCache


async def test_round_trip_and_remove(hass: HomeAssistant, hass_storage) -> None:
    cache = BrieflyCache(hass, "abc")
    await cache.async_load()
    assert not cache.has_history
    now = dt_util.utcnow()
    cache.mark_seen("s1", now)
    cache.set_done("s1", ["para"], ["fact"])
    cache.block_host("example.com", now)
    await cache.async_save()
    assert hass_storage["briefly_cache.abc"]["data"]["summaries"]["s1"]["status"] == "done"

    again = BrieflyCache(hass, "abc")
    await again.async_load()
    assert again.is_seen("s1") and again.has_history
    assert again.get_summary("s1")["summary"] == ["para"]
    assert again.host_blocked("example.com", now)
    await again.async_remove()
    assert "briefly_cache.abc" not in hass_storage


async def test_block_expires(hass: HomeAssistant) -> None:
    cache = BrieflyCache(hass, "x")
    now = dt_util.utcnow()
    assert not cache.host_blocked("a.com", now)
    cache.block_host("a.com", now)
    assert not cache.host_blocked("a.com", now + timedelta(days=8))
    assert "a.com" not in cache.blocked


async def test_attempts_and_feed_only(hass: HomeAssistant) -> None:
    cache = BrieflyCache(hass, "x")
    assert cache.add_attempt("s") == 1
    assert cache.add_attempt("s") == 2
    cache.set_feed_only("s", "gave_up")
    assert cache.get_summary("s")["status"] == "feed_only"


async def test_prune(hass: HomeAssistant) -> None:
    cache = BrieflyCache(hass, "x")
    now = dt_util.utcnow()
    old = now - timedelta(days=10)
    cache.mark_seen("old", old)
    cache.mark_seen("old_but_listed", old)
    cache.mark_seen("fresh", now)
    cache.set_done("old", ["a"], [])
    cache.set_done("orphan", ["b"], [])
    cache.prune(now, keep={"old_but_listed"})
    assert set(cache.seen) == {"old_but_listed", "fresh"}
    assert cache.summaries == {}


async def test_schedule_save(hass: HomeAssistant, hass_storage, freezer) -> None:
    cache = BrieflyCache(hass, "later")
    cache.mark_seen("s", dt_util.utcnow())
    cache.schedule_save()
    freezer.tick(timedelta(seconds=11))
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert "s" in hass_storage["briefly_cache.later"]["data"]["seen"]
