"""Config and options flows for Briefly."""

from __future__ import annotations

import re
from typing import Any

import aiohttp
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    ColorRGBSelector,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import slugify
import voluptuous as vol

from .const import (
    ALEXA_MEDIA_DOMAIN,
    CONF_ADD_ANOTHER,
    CONF_ALEXA_ENABLED,
    CONF_ALEXA_TARGETS,
    CONF_COLOUR,
    CONF_CUSTOM_FEEDS,
    CONF_DEDUP,
    CONF_FEEDS,
    CONF_MAX_AGE_HOURS,
    CONF_MODEL,
    CONF_NAME,
    CONF_OLLAMA_URL,
    CONF_REFRESH_MINUTES,
    CONF_SECTION_ID,
    CONF_SECTION_NAME,
    CONF_SECTIONS,
    CONF_STORIES_PER_SECTION,
    CONF_SUMMARIES_PER_REFRESH,
    CONF_SUMMARY_LENGTH,
    CONF_SUMMARY_MODE,
    DEDUP_LEVELS,
    DEFAULT_COLOUR,
    DEFAULT_NAME,
    DEFAULT_OLLAMA_URL,
    DEFAULT_SETTINGS,
    DEFAULT_SUMMARY_LENGTH,
    DOMAIN,
    HTTP_TIMEOUT,
    MAX_AGE_RANGE,
    REFRESH_RANGE,
    STORIES_RANGE,
    SUMMARIES_RANGE,
    SUMMARY_LENGTHS,
    SUMMARY_MODES,
    SUMMARY_OFF,
    SUMMARY_OLLAMA,
    USER_AGENT,
)
from .feeds import FeedError, parse_feed
from .ollama import OllamaError, async_list_models, normalise_url
from .sources import PRESET_FEEDS, SUGGESTED_SECTIONS
from .speech import alexa_available

OLLAMA_DOWNLOAD_URL = "https://ollama.com/download"
OLLAMA_HA_DOCS_URL = "https://www.home-assistant.io/integrations/ollama/"
ALEXA_MEDIA_URL = "https://github.com/alandtse/alexa_media_player"
CONF_EDIT_SECTION = "edit_section_id"
CONF_DELETE = "delete"

_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


# Helpers --------------------------------------------------------------------
def hex_to_rgb(value: str) -> list[int]:
    """Return [r, g, b] for a #rrggbb colour."""
    match = _HEX.match(value or "") or _HEX.match(DEFAULT_COLOUR)
    digits = match.group(1)  # type: ignore[union-attr]
    return [int(digits[i : i + 2], 16) for i in (0, 2, 4)]


def rgb_to_hex(value: list[int] | str | None) -> str:
    """Return #rrggbb for an [r, g, b] colour."""
    if isinstance(value, str):
        return value if _HEX.match(value) else DEFAULT_COLOUR
    if not value or len(value) != 3:
        return DEFAULT_COLOUR
    return "#" + "".join(f"{max(0, min(255, int(c))):02x}" for c in value)


def split_urls(text: str | None) -> list[str]:
    """Split a block of text into URLs."""
    return [url for url in re.split(r"[\s,]+", text or "") if url]


def ollama_defaults(hass: HomeAssistant) -> tuple[str | None, str | None]:
    """Return the URL and model of Home Assistant's own Ollama integration."""
    for entry in hass.config_entries.async_entries("ollama"):
        url = entry.data.get("url")
        model = next(
            (sub.data.get("model") for sub in entry.subentries.values() if sub.data.get("model")),
            entry.options.get("model"),
        )
        return url, model
    return None, None


async def async_validate_feed(hass: HomeAssistant, url: str) -> bool:
    """Return True if the URL serves a valid RSS or Atom feed."""
    session = async_get_clientsession(hass)
    try:
        async with session.get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=HTTP_TIMEOUT),
        ) as resp:
            if resp.status != 200:
                return False
            body = await resp.read()
    except aiohttp.ClientError, TimeoutError:
        return False
    try:
        parsed = await hass.async_add_executor_job(parse_feed, body, None)
    except FeedError:
        return False
    return bool(parsed.stories)


def _preset_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=feed.key, label=feed.label) for feed in PRESET_FEEDS.values()
            ],
            multiple=True,
            mode=SelectSelectorMode.LIST,
        )
    )


def section_schema(
    defaults: dict[str, Any], *, add_another: bool, delete: bool = False
) -> vol.Schema:
    """Return the form for one section."""
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_SECTION_NAME, default=defaults.get(CONF_SECTION_NAME, "")
        ): TextSelector(),
        vol.Required(
            CONF_COLOUR, default=hex_to_rgb(defaults.get(CONF_COLOUR, DEFAULT_COLOUR))
        ): ColorRGBSelector(),
        vol.Optional(CONF_FEEDS, default=defaults.get(CONF_FEEDS, [])): _preset_selector(),
        vol.Optional(
            CONF_CUSTOM_FEEDS, default="\n".join(defaults.get(CONF_CUSTOM_FEEDS, []))
        ): TextSelector(TextSelectorConfig(multiline=True)),
    }
    if add_another:
        schema[vol.Required(CONF_ADD_ANOTHER, default=False)] = BooleanSelector()
    if delete:
        schema[vol.Required(CONF_DELETE, default=False)] = BooleanSelector()
    return vol.Schema(schema)


async def async_validate_section(
    hass: HomeAssistant,
    user_input: dict[str, Any],
    sections: list[dict[str, Any]],
    editing_id: str | None = None,
) -> tuple[dict[str, Any] | None, dict[str, str], dict[str, str]]:
    """Validate a section form; return (section, errors, placeholders)."""
    errors: dict[str, str] = {}
    placeholders: dict[str, str] = {}
    name = user_input.get(CONF_SECTION_NAME, "").strip()
    others = [s for s in sections if s[CONF_SECTION_ID] != editing_id]
    if not name:
        errors[CONF_SECTION_NAME] = "name_required"
    elif any(s[CONF_SECTION_NAME].casefold() == name.casefold() for s in others):
        errors[CONF_SECTION_NAME] = "name_exists"
    feeds = [key for key in user_input.get(CONF_FEEDS, []) if key in PRESET_FEEDS]
    custom = split_urls(user_input.get(CONF_CUSTOM_FEEDS))
    for url in custom:
        if not re.match(r"^https?://", url, re.IGNORECASE):
            errors[CONF_CUSTOM_FEEDS] = "invalid_url"
            placeholders["url"] = url
            break
        if not await async_validate_feed(hass, url):
            errors[CONF_CUSTOM_FEEDS] = "invalid_feed"
            placeholders["url"] = url
            break
    if not feeds and not custom and not errors:
        errors["base"] = "no_feeds"
    if errors:
        return None, errors, placeholders
    section_id = editing_id
    if section_id is None:
        taken = {s[CONF_SECTION_ID] for s in sections}
        base = slugify(name) or "section"
        section_id, n = base, 2
        while section_id in taken:
            section_id, n = f"{base}_{n}", n + 1
    return (
        {
            CONF_SECTION_ID: section_id,
            CONF_SECTION_NAME: name,
            CONF_COLOUR: rgb_to_hex(user_input.get(CONF_COLOUR)),
            CONF_FEEDS: feeds,
            CONF_CUSTOM_FEEDS: custom,
        },
        errors,
        placeholders,
    )


# Steps shared by the config flow and the options flow -----------------------
class _SharedSteps:
    """Summary and voice steps used by both flows."""

    hass: HomeAssistant
    _opts: dict[str, Any]
    _models: list[str]

    async def _after_summaries(self) -> ConfigFlowResult:  # pragma: no cover
        raise NotImplementedError

    async def _after_voice(self) -> ConfigFlowResult:  # pragma: no cover
        raise NotImplementedError

    async def async_step_summaries(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose whether stories are summarised by Ollama."""
        if user_input is not None:
            self._opts[CONF_SUMMARY_MODE] = user_input[CONF_SUMMARY_MODE]
            if user_input[CONF_SUMMARY_MODE] == SUMMARY_OLLAMA:
                return await self.async_step_ollama()
            return await self._after_summaries()
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="summaries",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SUMMARY_MODE,
                        default=self._opts.get(CONF_SUMMARY_MODE, SUMMARY_OFF),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=SUMMARY_MODES,
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_SUMMARY_MODE,
                        )
                    )
                }
            ),
            description_placeholders={"ollama_url": OLLAMA_DOWNLOAD_URL},
        )

    async def async_step_ollama(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Point Briefly at an Ollama server and read its models."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = normalise_url(user_input[CONF_OLLAMA_URL])
            try:
                models = await async_list_models(async_get_clientsession(self.hass), url)
            except OllamaError:
                errors["base"] = "cannot_connect"
            else:
                if models:
                    self._opts[CONF_OLLAMA_URL] = url
                    self._models = models
                    return await self.async_step_model()
                errors["base"] = "no_models"
        default_url, _model = ollama_defaults(self.hass)
        url = self._opts.get(CONF_OLLAMA_URL) or default_url or DEFAULT_OLLAMA_URL
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="ollama",
            data_schema=vol.Schema({vol.Required(CONF_OLLAMA_URL, default=url): TextSelector()}),
            errors=errors,
            description_placeholders={
                "ollama_url": OLLAMA_DOWNLOAD_URL,
                "ha_ollama_url": OLLAMA_HA_DOCS_URL,
            },
        )

    async def async_step_model(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick a model from the ones Ollama has installed."""
        if user_input is not None:
            self._opts[CONF_MODEL] = user_input[CONF_MODEL]
            self._opts[CONF_SUMMARY_LENGTH] = user_input[CONF_SUMMARY_LENGTH]
            return await self._after_summaries()
        _url, ha_model = ollama_defaults(self.hass)
        default = next(
            (m for m in (self._opts.get(CONF_MODEL), ha_model) if m in self._models),
            self._models[0],
        )
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="model",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_MODEL, default=default): SelectSelector(
                        SelectSelectorConfig(options=self._models, mode=SelectSelectorMode.DROPDOWN)
                    ),
                    vol.Required(
                        CONF_SUMMARY_LENGTH,
                        default=self._opts.get(CONF_SUMMARY_LENGTH, DEFAULT_SUMMARY_LENGTH),
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=SUMMARY_LENGTHS,
                            mode=SelectSelectorMode.LIST,
                            translation_key=CONF_SUMMARY_LENGTH,
                        )
                    ),
                }
            ),
            description_placeholders={"ha_model": ha_model or "-"},
        )

    async def async_step_voice(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Optionally speak headlines on Alexa devices via Alexa Media Player."""
        errors: dict[str, str] = {}
        if user_input is not None:
            enabled = user_input[CONF_ALEXA_ENABLED]
            targets = user_input.get(CONF_ALEXA_TARGETS, [])
            if enabled and not alexa_available(self.hass):
                errors["base"] = "alexa_media_missing"
            elif enabled and not targets:
                errors[CONF_ALEXA_TARGETS] = "targets_required"
            else:
                self._opts[CONF_ALEXA_ENABLED] = enabled
                self._opts[CONF_ALEXA_TARGETS] = targets if enabled else []
                return await self._after_voice()
        return self.async_show_form(  # type: ignore[attr-defined]
            step_id="voice",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_ALEXA_ENABLED,
                        default=self._opts.get(CONF_ALEXA_ENABLED, False),
                    ): BooleanSelector(),
                    vol.Optional(
                        CONF_ALEXA_TARGETS,
                        default=self._opts.get(CONF_ALEXA_TARGETS, []),
                    ): EntitySelector(
                        EntitySelectorConfig(
                            domain="media_player",
                            integration=ALEXA_MEDIA_DOMAIN,
                            multiple=True,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={"alexa_media_url": ALEXA_MEDIA_URL},
        )


# Config flow ----------------------------------------------------------------
class BrieflyConfigFlow(_SharedSteps, ConfigFlow, domain=DOMAIN):
    """Set up a news desk."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the flow."""
        self._name = DEFAULT_NAME
        self._sections: list[dict[str, Any]] = []
        self._opts: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self._models: list[str] = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> BrieflyOptionsFlow:
        """Return the options flow."""
        return BrieflyOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Name the desk."""
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not name:
                errors[CONF_NAME] = "name_required"
            else:
                await self.async_set_unique_id(slugify(name))
                self._abort_if_unique_id_configured()
                self._name = name
                return await self.async_step_section()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_NAME, default=DEFAULT_NAME): TextSelector()}),
            errors=errors,
        )

    async def async_step_section(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add a section: name, colour and the news sources it shows."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"url": ""}
        defaults: dict[str, Any] = {}
        if user_input is not None:
            section, errors, extra = await async_validate_section(
                self.hass, user_input, self._sections
            )
            placeholders.update(extra)
            if section is not None:
                self._sections.append(section)
                if user_input.get(CONF_ADD_ANOTHER):
                    return await self.async_step_section()
                return await self.async_step_summaries()
            defaults = {
                **user_input,
                CONF_COLOUR: rgb_to_hex(user_input.get(CONF_COLOUR)),
                CONF_CUSTOM_FEEDS: split_urls(user_input.get(CONF_CUSTOM_FEEDS)),
            }
        elif len(self._sections) < len(SUGGESTED_SECTIONS):
            name, colour, feeds = SUGGESTED_SECTIONS[len(self._sections)]
            defaults = {CONF_SECTION_NAME: name, CONF_COLOUR: colour, CONF_FEEDS: feeds}
        placeholders["count"] = str(len(self._sections))
        return self.async_show_form(
            step_id="section",
            data_schema=section_schema(defaults, add_another=True),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _after_summaries(self) -> ConfigFlowResult:
        return await self.async_step_voice()

    async def _after_voice(self) -> ConfigFlowResult:
        return self.async_create_entry(
            title=self._name,
            data={CONF_NAME: self._name},
            options={**self._opts, CONF_SECTIONS: self._sections},
        )


# Options flow ---------------------------------------------------------------
class BrieflyOptionsFlow(_SharedSteps, OptionsFlowWithReload):
    """Change a news desk after setup."""

    def __init__(self) -> None:
        """Initialise the options flow."""
        self._opts: dict[str, Any] = {}
        self._models: list[str] = []
        self._editing: str | None = None

    @property
    def _sections(self) -> list[dict[str, Any]]:
        return self._opts.setdefault(CONF_SECTIONS, [])

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu."""
        self._opts = {**DEFAULT_SETTINGS, **self.config_entry.options}
        self._opts[CONF_SECTIONS] = [
            dict(s) for s in self.config_entry.options.get(CONF_SECTIONS, [])
        ]
        return self.async_show_menu(
            step_id="init",
            menu_options=["settings", "add_section", "edit_section", "summaries", "voice"],
        )

    def _save(self) -> ConfigFlowResult:
        return self.async_create_entry(data=self._opts)

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Refresh interval, story counts, age and duplicate threshold."""
        if user_input is not None:
            self._opts.update(
                {
                    key: int(value) if key != CONF_DEDUP else value
                    for key, value in user_input.items()
                }
            )
            return self._save()

        def number(key: str, bounds: tuple[int, int], unit: str) -> tuple[Any, Any]:
            return (
                vol.Required(key, default=self._opts[key]),
                NumberSelector(
                    NumberSelectorConfig(
                        min=bounds[0],
                        max=bounds[1],
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement=unit,
                    )
                ),
            )

        fields = dict(
            [
                number(CONF_REFRESH_MINUTES, REFRESH_RANGE, "min"),
                number(CONF_STORIES_PER_SECTION, STORIES_RANGE, "stories"),
                number(CONF_MAX_AGE_HOURS, MAX_AGE_RANGE, "h"),
                number(CONF_SUMMARIES_PER_REFRESH, SUMMARIES_RANGE, "stories"),
            ]
        )
        fields[vol.Required(CONF_DEDUP, default=self._opts[CONF_DEDUP])] = SelectSelector(
            SelectSelectorConfig(
                options=DEDUP_LEVELS, mode=SelectSelectorMode.LIST, translation_key=CONF_DEDUP
            )
        )
        return self.async_show_form(step_id="settings", data_schema=vol.Schema(fields))

    async def async_step_add_section(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add another section."""
        errors: dict[str, str] = {}
        placeholders = {"url": ""}
        defaults: dict[str, Any] = {}
        if user_input is not None:
            section, errors, extra = await async_validate_section(
                self.hass, user_input, self._sections
            )
            placeholders.update(extra)
            if section is not None:
                self._sections.append(section)
                return self._save()
            defaults = {**user_input, CONF_COLOUR: rgb_to_hex(user_input.get(CONF_COLOUR))}
            defaults[CONF_CUSTOM_FEEDS] = split_urls(user_input.get(CONF_CUSTOM_FEEDS))
        return self.async_show_form(
            step_id="add_section",
            data_schema=section_schema(defaults, add_another=False),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_edit_section(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a section to change or remove."""
        if user_input is not None:
            self._editing = user_input[CONF_EDIT_SECTION]
            return await self.async_step_section_details()
        if not self._sections:
            return self.async_abort(reason="no_sections")
        return self.async_show_form(
            step_id="edit_section",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_EDIT_SECTION, default=self._sections[0][CONF_SECTION_ID]
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=[
                                SelectOptionDict(
                                    value=s[CONF_SECTION_ID], label=s[CONF_SECTION_NAME]
                                )
                                for s in self._sections
                            ],
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_section_details(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change or remove one section. Cached summaries are kept either way."""
        index = next(i for i, s in enumerate(self._sections) if s[CONF_SECTION_ID] == self._editing)
        current = self._sections[index]
        errors: dict[str, str] = {}
        placeholders = {"url": "", "section": current[CONF_SECTION_NAME]}
        defaults: dict[str, Any] = current
        if user_input is not None:
            if user_input.get(CONF_DELETE):
                if len(self._sections) == 1:
                    errors["base"] = "last_section"
                else:
                    del self._sections[index]
                    return self._save()
            else:
                section, errors, extra = await async_validate_section(
                    self.hass, user_input, self._sections, editing_id=self._editing
                )
                placeholders.update(extra)
                if section is not None:
                    self._sections[index] = section
                    return self._save()
            defaults = {
                **user_input,
                CONF_COLOUR: rgb_to_hex(user_input.get(CONF_COLOUR)),
                CONF_CUSTOM_FEEDS: split_urls(user_input.get(CONF_CUSTOM_FEEDS)),
            }
        return self.async_show_form(
            step_id="section_details",
            data_schema=section_schema(defaults, add_another=False, delete=True),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _after_summaries(self) -> ConfigFlowResult:
        return self._save()

    async def _after_voice(self) -> ConfigFlowResult:
        return self._save()
