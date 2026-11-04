"""The image proxy."""

from __future__ import annotations

import os
from pathlib import Path
import time

from homeassistant.core import HomeAssistant

from custom_components.briefly.image_proxy import image_cache_dir, prune_image_cache

from .helpers import CONNECTION_ERROR, make_entry, register_feeds, setup_entry

SMALL = "https://ichef.bbci.co.uk/ace/standard/480/cpsprodpb/aaa/live/homes.jpg"
LARGE = "https://ichef.bbci.co.uk/ace/standard/976/cpsprodpb/aaa/live/homes.jpg"


async def test_proxy_serves_and_caches(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    aioclient_mock.get(SMALL, content=b"small-jpeg", headers={"Content-Type": "image/jpeg"})
    aioclient_mock.get(LARGE, content=b"large-jpeg", headers={"Content-Type": "image/jpeg"})
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry())
    lead = hass.states.get("sensor.kiosk_news_uk").attributes["stories"][0]
    client = await hass_client_no_auth()

    resp = await client.get(lead["image"])
    assert resp.status == 200
    assert await resp.read() == b"small-jpeg"
    assert resp.headers["Content-Type"] == "image/jpeg"
    resp = await client.get(lead["image_large"])
    assert await resp.read() == b"large-jpeg"

    aioclient_mock.clear_requests()
    resp = await client.get(lead["image"])
    assert await resp.read() == b"small-jpeg"
    assert aioclient_mock.call_count == 0  # served from the disk cache


async def test_proxy_unknown_and_failing(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    aioclient_mock.get(SMALL, exc=CONNECTION_ERROR)
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry())
    stories = hass.states.get("sensor.kiosk_news_uk").attributes["stories"]
    client = await hass_client_no_auth()
    assert (await client.get("/api/briefly/image/unknown")).status == 404
    assert (await client.get(stories[0]["image"])).status == 502
    no_image = next(s for s in stories if s["image"] is None)
    assert (await client.get(f"/api/briefly/image/{no_image['id']}")).status == 404


async def test_prune_image_cache(tmp_path) -> None:
    folder = tmp_path / "cache"
    assert prune_image_cache(folder, 10) == 0
    folder.mkdir()
    old, meta, fresh = folder / "old", folder / "old.json", folder / "fresh"
    for file in (old, meta, fresh):
        file.write_bytes(b"x")
    past = time.time() - 100
    os.utime(old, (past, past))
    os.utime(meta, (past, past))
    assert prune_image_cache(folder, 10) == 1
    assert not old.exists()
    assert not meta.exists()
    assert fresh.exists()


async def test_expired_cache_entry_is_refetched(
    hass: HomeAssistant, hass_client_no_auth, aioclient_mock
) -> None:
    aioclient_mock.get(SMALL, content=b"v1", headers={"Content-Type": "image/jpeg"})
    register_feeds(aioclient_mock)
    await setup_entry(hass, make_entry())
    lead = hass.states.get("sensor.kiosk_news_uk").attributes["stories"][0]
    client = await hass_client_no_auth()
    await client.get(lead["image"])
    from custom_components.briefly import image_proxy

    cache = image_proxy.image_cache_dir(hass)  # the patched temp dir
    for file in cache.iterdir():
        os.utime(file, (0, 0))
    aioclient_mock.clear_requests()
    aioclient_mock.get(SMALL, content=b"v2", headers={"Content-Type": "image/jpeg"})
    assert await (await client.get(lead["image"])).read() == b"v2"


def test_image_cache_dir(hass: HomeAssistant) -> None:
    """The real location (imported before the autouse patch applies)."""
    assert image_cache_dir(hass) == Path(hass.config.path(".cache/briefly_images"))
