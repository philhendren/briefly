# Briefly

Briefly is a Home Assistant news integration. It turns RSS and Atom feeds into a sorted, de-duplicated news desk, with optional short summaries written by your own local [Ollama](https://ollama.com) model and optional spoken headlines on Amazon Echo devices.

- **UI only:** no YAML. Add it under **Settings → Devices & services → Add integration → Briefly**.
- **Sections:** group feeds into named columns (UK, Politics, Sport…), each with its own colour.
- **De-duplication:** when several outlets carry the same story, it shows once, with "also reported by".
- **Thumbnails:** served through Home Assistant's own image proxy, so dashboards never contact third-party image servers.
- **Optional AI summaries:** written once per story by a model you pick from your Ollama server, checked for invented numbers, then cached.
- **Works without AI:** with summaries off, each story shows its feed's own description.
- **Optional spoken headlines:** through Alexa Media Player (a separate integration, see below).

## Installation

### HACS (custom repository)

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/philhendren/briefly` with the type **Integration**.
2. Install **Briefly** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → Briefly**.

### Manual

Copy `custom_components/briefly` into your Home Assistant `config/custom_components/` folder, restart, then add the integration as above.

## Setup

One Briefly entry is one **news desk**. Setup takes a few short steps:

1. **Name the desk**, for example "Kiosk news". Entities are named after it (`sensor.kiosk_news_uk`).
2. **Add sections.** Give each a name and colour, then tick its news sources from the list. You can also paste any other RSS or Atom feed URL; Briefly checks that it is a working feed before saving. Tick **Add another section** to keep going.
3. **Summaries.** Choose **Off** or **Ollama**. With Ollama, enter your server's address and pick a model from the drop-down. The list comes from your Ollama server itself.
4. **Spoken headlines (optional).** Turn on and choose your Echo devices. This needs Alexa Media Player.

Everything can be changed later with the integration's **Configure** button: refresh interval, stories per section, maximum age, duplicate threshold, summaries per refresh, and adding, changing or removing sections. Cached summaries survive section changes.

| Option | Default | Range |
|---|---|---|
| Refresh interval | 30 min | 10–240 min |
| Stories kept per section | 10 | 3–25 |
| Maximum story age | 48 h | 6–168 h |
| Duplicate threshold | Normal | Off / Loose / Normal / Strict |
| Summaries per refresh | 8 | 1–30 |
| Summary length | Short (90–140 words) | Headline only / Short / Medium |

### News sources

Every preset was checked on 2026-11-04: the feed is public, the publisher's `robots.txt` allows its article pages for an honest automated reader, and a request with Briefly's user agent succeeds. That matters because summaries need the article text.

| Publisher | Sections offered |
|---|---|
| BBC News / BBC Sport | UK, Politics, World, Business, Technology, Science & Environment, Health, Sport |
| The Guardian | UK, Politics, World, Business, Technology, Environment, Sport |
| The Standard | UK, Politics, Sport |
| Al Jazeera | All news |
| NPR | News, World |
| The Conversation | UK |
| City AM | Business |

Publishers that refuse automated article fetching are not offered: **Sky News** (HTTP 403) and **The Telegraph** (HTTP 402, paywall). If a site starts refusing later, Briefly notices and shows feed text only for that site for 7 days.

## Optional: Ollama summaries

Summaries are off unless you choose them. Briefly talks to Ollama directly, so you can pick any model installed on your server.

**Need Ollama?**

- Download and install it: <https://ollama.com/download> (Windows, macOS, Linux, or [Docker](https://hub.docker.com/r/ollama/ollama)).
- Pull a model, for example `ollama pull qwen3:14b` or the smaller `ollama pull llama3.2:3b`. Browse models at <https://ollama.com/search>.
- If Home Assistant runs on a different machine from Ollama, make Ollama listen on your network (set `OLLAMA_HOST=0.0.0.0`), see the [Ollama FAQ](https://github.com/ollama/ollama/blob/main/docs/faq.md#how-do-i-configure-ollama-server).
- Home Assistant's own [Ollama integration](https://www.home-assistant.io/integrations/ollama/) is optional. If you have it, Briefly fills in its server address and pre-selects the same model, so a second model isn't loaded onto your GPU.

**How a story is summarised**

1. A new story reaches a section's top stories. Section leads go first, and at most *Summaries per refresh* stories are sent each refresh.
2. Briefly fetches the article page once and keeps only its readable paragraphs (about 7,000 characters at most).
3. It asks your model for 2–3 short paragraphs and up to 3 key facts, as structured JSON. The rules: only facts stated in the article, British English, plain and neutral, names, numbers and quotes exactly as written.
4. **Every number in the summary must appear in the article.** If one doesn't, the summary is thrown away and the story shows its feed description.
5. The summary is cached in `.storage/briefly_cache.<entry id>` and the article text is discarded. Each story is summarised once.

If Ollama is unavailable, the story stays `pending` and is retried at the next refresh, up to 3 times.

## Optional: spoken headlines on Alexa

> **Alexa Media Player is a separate custom integration.** It is not part of Briefly or of Home Assistant. Install it yourself from HACS: <https://github.com/alandtse/alexa_media_player>. Briefly only calls its `notify.alexa_media` service, and only when you turn spoken headlines on.

Once Alexa Media Player is set up, turn on **Spoken headlines** (during setup or under **Configure**) and choose your Echo devices. Then call the action:

```yaml
action: briefly.speak_headlines
data:
  section: UK      # optional
  count: 3         # optional, 1–10
```

Alexa says, for example: *"Here are the top 3 headlines from UK news. From BBC News: …"*.

To start it by voice, put the action in a script and expose the script to Alexa (through Home Assistant Cloud or the Alexa Smart Home skill), or trigger it from an Alexa routine.

## What it creates

Each desk is one device with these entities:

| Entity | State | Attributes |
|---|---|---|
| `sensor.<desk>_<section>` (one per section) | Number of stories | `stories` (list), `sources`, `colour` |
| `sensor.<desk>_last_updated` | Time of the last refresh | `summarised`, `pending`, `errors` |
| `event.<desk>_new_story` | Fires once per new story | `section`, `title`, `source`, `link`, `story_id` |
| `button.<desk>_refresh` | Press to refresh now | |

Story lists are kept out of the recorder, so the database doesn't grow. Each story looks like this:

```json
{
  "id": "b535275147",
  "title": "Miliband says slavery apology will not bring cost for UK taxpayers",
  "description": "Speaking to BBC's Newscast, the foreign secretary says...",
  "source": "BBC News",
  "link": "https://www.bbc.co.uk/news/articles/cm8ezneewr9lo",
  "image": "/api/briefly/image/b535275147?size=small",
  "image_large": "/api/briefly/image/b535275147?size=large",
  "published": "2026-11-04T02:14:45+00:00",
  "summary": ["Foreign Secretary Ed Miliband said...", "..."],
  "key_facts": ["..."],
  "summary_status": "done",
  "also_reported_by": ["The Guardian"]
}
```

`summary_status` is `done`, `pending`, `off` (summaries disabled) or `feed_only` (the publisher blocks article fetching, the article had no readable text, the summary failed the number check, or Ollama failed 3 times).

### Actions

- `briefly.refresh`: fetch the feeds now.
- `briefly.get_stories`: returns stories as a response, filtered by section and count. Use it in scripts and voice.
- `briefly.summarise`: summarise one story now, by `story_id`.
- `briefly.speak_headlines`: read headlines on Echo devices (needs Alexa Media Player).

### Image proxy

`/api/briefly/image/<id>?size=small|large` serves each thumbnail through Home Assistant and caches it on disk for 48 hours. It only serves images for stories Briefly currently lists, so it can't be used as an open proxy.

## Respecting publishers

- **Honest user agent:** `HomeAssistant-Briefly/<version> (+https://github.com/philhendren/briefly)`. It never pretends to be a browser.
- **robots.txt:** checked once a day per site. A disallowed article path means no article fetch.
- **Refusals:** HTTP 401, 402, 403 or 429 marks the site feed-only for 7 days.
- **Light load:** one feed request per refresh with `ETag` / `Last-Modified`, and at most one article request per story, ever.
- **Attribution:** every story keeps its source and link.
- **Private use:** summaries stay inside your Home Assistant. There is no sharing or export feature.

## Development

```bash
uv venv -p 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/pytest
```

The suite has unit tests and BDD scenarios (`tests/bdd/features/*.feature`, run with pytest-bdd). It requires 100% line and branch coverage. Every HTTP call, including Ollama, is mocked; real network access is blocked during tests.
