"""LLM model alias resolution and the OpenRouter / OpenAI client factory (LLM_PROVIDER)."""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.core import llm_models
from app.deps import get_settings

if TYPE_CHECKING:
    # openai is the `llm` optional dependency — imported lazily inside
    # get_llm_client() so the module loads on deploys that didn't install it.
    from openai import AsyncOpenAI

# Aliases that work with `add_context_from_internet=True`. Base44's refusal
# names only `gemini_3_8_flash` today (2026-09-17), yet `gemini_3_flash` and
# `gemini_3_1_pro` still answer grounded (measured, citations and all) — the
# accept set is a superset of the reported one, like the model list.
# `automatic` and `None` resolve to WEB_SEARCH_DEFAULT_ALIAS before sending
# (D-022's rule; the alias moved with Base44's reported one).
WEB_SEARCH_COMPATIBLE = {"gemini_3_8_flash", "gemini_3_flash", "gemini_3_1_pro", "automatic", None}
WEB_SEARCH_DEFAULT_ALIAS = "gemini_3_8_flash"

# Base44 docs (Building-your-app/AI-agents-for-apps, read 2026-08-23): "The
# default Automatic option (based on Gemini 3.1 Flash Lite)". Corroborated by
# the AI gateway's credit tiers the same day: automatic bills 1.0 credit vs
# gemini_3_flash's 2.5 — a cheaper Gemini tier, i.e. NOT flash. (The doc said
# "Gemini 2.5 Flash" when this previously mapped to gemini_3_flash; Base44
# moved the tier and we follow.) Flash Lite has no Base44 alias, so automatic
# resolves straight to the provider slug — checked against OpenRouter's live
# catalog 2026-08-23 (GA slug, 1M context, tools+vision).
AUTOMATIC_PROVIDER = "google/gemini-3.1-flash-lite"


# LLM_PROVIDER == "openai": every Base44 alias resolves to this ONE model on
# the app owner's own OpenAI key (the HIPAA lineup — OpenAI signs a BAA for
# the API; OpenRouter signs none). One model, not a per-alias table: the
# owner bought "AI under a BAA", and a table of near-equivalents is a second
# catalog to drift (Daniel, 2026-09-06). gpt-5.4 is what Base44 itself routes
# the `gpt_5` alias to today; vision, tools, JSON schema and PDF inputs all
# work on it. Checked against OpenAI's live model list on 2026-09-06.
OPENAI_CHAT_MODEL = "gpt-5.4"
OPENAI_IMAGE_MODEL = "gpt-image-1"

# Base44's GenerateVideo is Google Veo 3.1 through Vertex AI — measured
# 2026-09-17: its request contract is Veo 3.1's exact parameter set
# (duration 4|6|8, aspect 16:9|9:16, generate_audio), the produced MP4 carries
# `encoder: Google`, and a refused prompt returns Vertex's own filter text.
# Which Veo 3.1 TIER Base44 runs is not observable from outside (same
# encoder, same shapes; generation times overlap — 33 s at Base44 vs 29–50 s
# lite / 41–81 s fast / 60–70 s full for the same 4 s clip on OpenRouter).
# Lite is the tier whose per-second price sits nearest what Base44 bills its
# own users (5 credits/s ≈ $0.025/s on Builder; lite $0.05/s at 720p with
# audio, fast $0.10, full $0.40), so a migrated app's owner pays roughly what
# the feature cost them before. Checked against OpenRouter's live video
# catalog (GET /api/v1/videos/models) on 2026-09-17: durations [4, 6, 8],
# resolutions 720p/1080p, aspect ratios 16:9/9:16, audio switchable — the
# whole Base44 contract is expressible on it without translation.
VIDEO_PROVIDER = "google/veo-3.1-lite"
# Base44 has no resolution parameter; every measured clip was 720p.
VIDEO_RESOLUTION = "720p"


def llm_provider() -> str:
    return get_settings().LLM_PROVIDER


def is_openrouter() -> bool:
    return llm_provider() == "openrouter"


def supports_web_grounding() -> bool:
    """Gemini's `googleSearch` grounding rides OpenRouter only. Under the
    OpenAI provider a grounded request is answered WITHOUT grounding, never
    refused: OpenAI's own web search is outside its BAA."""
    return is_openrouter()


@lru_cache(maxsize=1)
def get_llm_client() -> AsyncOpenAI:
    """One OpenAI-compatible client, pointed by LLM_PROVIDER: OpenRouter (the
    default) or OpenAI's own endpoint on OPENAI_API_KEY."""
    from openai import AsyncOpenAI

    settings = get_settings()
    if settings.LLM_PROVIDER == "openai":
        return AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return AsyncOpenAI(
        api_key=settings.OPENROUTER_API_KEY,
        base_url=settings.OPENROUTER_BASE_URL,
    )


def resolve_model(alias: str | None, app_settings: dict) -> tuple[str, str]:
    """Returns (model_string, effective_alias) for use as the `model` param in chat.completions.create()."""
    if not is_openrouter():
        return OPENAI_CHAT_MODEL, alias or "automatic"

    if alias is None or alias == "automatic":
        app_model = app_settings.get("model")
        if app_model and app_model in llm_models.ALIASES:
            effective = app_model
        else:
            return AUTOMATIC_PROVIDER, "automatic"
    else:
        effective = alias

    return (effective if "/" in effective else llm_models.route(effective)), effective
