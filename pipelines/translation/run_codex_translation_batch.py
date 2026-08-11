#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

OPENCLAW_CONFIG = Path("/home/node/.openclaw/openclaw.json")
AUTH_PROFILES_PATH = Path("/home/node/.openclaw/agents/main/agent/auth-profiles.json")
MODELS_CONFIG_PATH = Path("/home/node/.openclaw/agents/main/agent/models.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _materialize_secret(raw: Any) -> str:
    if not isinstance(raw, str):
        return ""
    s = raw.strip()
    if not s:
        return ""
    if s.startswith("${") and s.endswith("}"):
        return (os.environ.get(s[2:-1]) or "").strip()
    if s.startswith("$") and len(s) > 1:
        return (os.environ.get(s[1:]) or "").strip()
    return s


def _resolve_openai_api_key(auth_profile: str | None = None) -> str:
    candidates: list[Any] = []

    # 1) Explicit OpenClaw auth profile selection first (preferred for funded identity routing).
    if AUTH_PROFILES_PATH.exists():
        try:
            ap = _read_json(AUTH_PROFILES_PATH)
            profiles = ap.get("profiles") if isinstance(ap, dict) else None
            if isinstance(profiles, dict):
                if auth_profile:
                    p = profiles.get(auth_profile)
                    if isinstance(p, dict):
                        provider = str(p.get("provider") or "").lower()
                        if provider in {"openai", "openai-codex"}:
                            candidates.extend([p.get("apiKey"), p.get("key"), p.get("access")])
                # try yaqub0r codex profile by convention if explicit profile not supplied
                if not auth_profile:
                    yp = profiles.get("openai-codex:yaqub0r")
                    if isinstance(yp, dict):
                        candidates.extend([yp.get("apiKey"), yp.get("key"), yp.get("access")])
                # then other openai/openai-codex profiles
                for _, profile in profiles.items():
                    if not isinstance(profile, dict):
                        continue
                    provider = str(profile.get("provider") or "").lower()
                    if provider in {"openai", "openai-codex"}:
                        candidates.extend([profile.get("apiKey"), profile.get("key"), profile.get("access")])
        except Exception:
            pass

    # 2) OpenClaw provider config
    if OPENCLAW_CONFIG.exists():
        try:
            cfg = _read_json(OPENCLAW_CONFIG)
            providers = ((cfg.get("models") or {}).get("providers") or {}) if isinstance(cfg, dict) else {}
            if isinstance(providers, dict):
                for provider_name in ("openai-codex", "openai"):
                    p = providers.get(provider_name)
                    if isinstance(p, dict):
                        candidates.extend([p.get("apiKey"), p.get("key"), p.get("access")])
        except Exception:
            pass

    # 3) Raw env vars as last resort
    direct = (
        os.getenv("OPENAI_API_KEY")
        or os.getenv("OPENCLAW_OPENAI_API_KEY")
        or os.getenv("OPENAI_KEY")
        or os.getenv("OPENAI_ACCESS_TOKEN")
        or ""
    ).strip()
    if direct:
        candidates.append(direct)

    for c in candidates:
        s = _materialize_secret(c)
        if s:
            return s
    return ""


def _resolve_openai_base_url() -> str:
    direct = (os.getenv("OPENAI_BASE_URL") or "").strip()
    if direct:
        return direct.rstrip("/")

    # Prefer active OpenClaw agent models config first.
    if MODELS_CONFIG_PATH.exists():
        try:
            cfg = _read_json(MODELS_CONFIG_PATH)
            providers = cfg.get("providers") if isinstance(cfg, dict) else None
            if isinstance(providers, dict):
                for provider_name in ("openai-codex", "openai"):
                    p = providers.get(provider_name)
                    if isinstance(p, dict):
                        for k in ("baseUrl", "apiBaseUrl", "url"):
                            v = _materialize_secret(p.get(k))
                            if v:
                                return v.rstrip("/")
        except Exception:
            pass

    if OPENCLAW_CONFIG.exists():
        try:
            cfg = _read_json(OPENCLAW_CONFIG)
            providers = ((cfg.get("models") or {}).get("providers") or {}) if isinstance(cfg, dict) else {}
            if isinstance(providers, dict):
                for provider_name in ("openai-codex", "openai"):
                    p = providers.get(provider_name)
                    if isinstance(p, dict):
                        for k in ("baseUrl", "apiBaseUrl", "url"):
                            v = _materialize_secret(p.get(k))
                            if v:
                                return v.rstrip("/")
        except Exception:
            pass

    return "https://api.openai.com/v1"


def _normalize_model(model: str) -> str:
    m = (model or "").strip()
    if not m:
        return "gpt-5.3-codex"
    if "/" in m:
        provider, rest = m.split("/", 1)
        if provider.lower() in {"openai", "openai-codex"} and rest.strip():
            return rest.strip()
    if m.lower() == "codex":
        return "gpt-5.3-codex"
    return m


def _resolve_openrouter_api_key() -> str:
    direct = (os.getenv("OPENROUTER_API_KEY") or "").strip()
    if direct:
        return direct

    candidates: list[Any] = []

    if MODELS_CONFIG_PATH.exists():
        try:
            cfg = _read_json(MODELS_CONFIG_PATH)
            providers = cfg.get("providers") if isinstance(cfg, dict) else None
            if isinstance(providers, dict):
                p = providers.get("openrouter")
                if isinstance(p, dict):
                    candidates.extend([p.get("apiKey"), p.get("key")])
        except Exception:
            pass

    if AUTH_PROFILES_PATH.exists():
        try:
            ap = _read_json(AUTH_PROFILES_PATH)
            profiles = ap.get("profiles") if isinstance(ap, dict) else None
            if isinstance(profiles, dict):
                for _, profile in profiles.items():
                    if not isinstance(profile, dict):
                        continue
                    provider = str(profile.get("provider") or "").lower()
                    if provider == "openrouter":
                        candidates.extend([profile.get("apiKey"), profile.get("key")])
        except Exception:
            pass

    for c in candidates:
        s = _materialize_secret(c)
        if s:
            return s
    return ""


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _append_jsonl(path: Path, rec: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"completed": {}, "failed": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_glossary(path: Path | None) -> list[dict[str, str]]:
    if not path:
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        out = []
        for x in data:
            if isinstance(x, dict):
                src = str(x.get("source") or "").strip()
                tgt = str(x.get("target") or "").strip()
                if src and tgt:
                    out.append({"source": src, "target": tgt})
        return out
    return []


def _render_glossary(glossary: list[dict[str, str]]) -> str:
    if not glossary:
        return ""
    lines = ["Glossary (enforce these mappings where contextually applicable):"]
    for g in glossary:
        lines.append(f"- {g['source']} => {g['target']}")
    return "\n".join(lines)


def _build_messages(chunk: dict[str, Any], style: str, glossary: list[dict[str, str]]) -> list[dict[str, str]]:
    source_lang = chunk.get("source_lang") or "ar"
    target_lang = chunk.get("target_lang") or "en"
    gtxt = _render_glossary(glossary)

    system = (
        "You are a careful literary-historical translator. "
        "Output only the translated text, no notes, no commentary. "
        "Preserve paragraph boundaries and ordering. "
        "Do not omit content. Do not summarize."
    )

    user = (
        f"Translate from {source_lang} to {target_lang}.\\n"
        f"Style: {style}.\\n"
        "Rules:\\n"
        "- Keep proper names consistent across chunks.\\n"
        "- Keep isnad/narration wording faithful; do not modernize theological meaning.\\n"
        "- Preserve quotes and structural markers where present.\\n"
    )
    if gtxt:
        user += gtxt + "\\n"

    user += "\\nSource text:\\n" + str(chunk.get("source_text") or "")

    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_text_from_response(payload: dict[str, Any]) -> str:
    # Chat Completions format
    choices = payload.get("choices") or []
    if choices:
        msg = (choices[0] or {}).get("message") or {}
        content = msg.get("content")
        if isinstance(content, str):
            return content.strip()
    raise RuntimeError("unable to extract translation text from API response")


def _call_openrouter_chat(model: str, messages: list[dict[str, str]], timeout_s: int = 180) -> dict[str, Any]:
    key = _resolve_openrouter_api_key()
    if not key:
        raise RuntimeError("OpenRouter fallback unavailable: missing key")

    fallback_model = _normalize_model(model)
    if "/" not in fallback_model:
        fallback_model = f"openai/{fallback_model}"

    req = urllib.request.Request(
        url="https://openrouter.ai/api/v1/chat/completions",
        data=json.dumps({"model": fallback_model, "messages": messages, "temperature": 0.2}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://openclaw.local",
            "X-Title": "firstlight-translation-batch",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _call_chat(
    model: str,
    messages: list[dict[str, str]],
    timeout_s: int = 180,
    auth_profile: str | None = None,
    allow_openrouter_fallback: bool = True,
) -> dict[str, Any]:
    key = _resolve_openai_api_key(auth_profile=auth_profile)
    if not key:
        raise RuntimeError("OPENAI/OpenClaw API key is required")
    base = _resolve_openai_base_url()

    body = {
        "model": _normalize_model(model),
        "messages": messages,
        "temperature": 0.2,
    }
    req = urllib.request.Request(
        url=f"{base}/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8", errors="ignore"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", errors="ignore")[:1200]
        except Exception:
            detail = str(e)

        fallback_codes = {401, 403, 429, 500, 502, 503, 504}
        if allow_openrouter_fallback and e.code in fallback_codes:
            # mirror recommend_books pattern: fallback when primary OpenAI/Codex path is blocked.
            return _call_openrouter_chat(model, messages, timeout_s=timeout_s)
        raise RuntimeError(f"HTTP {e.code}: {detail}") from e


def main() -> None:
    ap = argparse.ArgumentParser(description="Run resumable Codex translation batch over chunk manifest.")
    ap.add_argument("--chunks", required=True, help="Chunk manifest JSONL.")
    ap.add_argument("--out", required=True, help="Output translations JSONL.")
    ap.add_argument("--state", required=True, help="State file (resume tracking).")
    ap.add_argument("--model", default="codex")
    ap.add_argument("--auth-profile", default="openai-codex:yaqub0r", help="OpenClaw auth profile key (e.g., openai-codex:yaqub0r)")
    ap.add_argument("--style", default="faithful", choices=["faithful", "readable"])
    ap.add_argument("--no-openrouter-fallback", action="store_true", help="Disable OpenRouter fallback when primary codex auth path fails")
    ap.add_argument("--glossary", help="Optional glossary JSON file [{source,target}, ...]")
    ap.add_argument("--max-retries", type=int, default=3)
    ap.add_argument("--sleep-ms", type=int, default=800)
    ap.add_argument("--limit", type=int, default=0, help="Optional max chunks for this run")
    args = ap.parse_args()

    chunks = _load_jsonl(Path(args.chunks))
    out_path = Path(args.out)
    state_path = Path(args.state)
    glossary = _load_glossary(Path(args.glossary) if args.glossary else None)

    state = _load_state(state_path)
    completed: dict[str, Any] = state.setdefault("completed", {})
    failed: dict[str, Any] = state.setdefault("failed", {})

    pending = [c for c in chunks if str(c.get("chunk_id")) not in completed]
    if args.limit and args.limit > 0:
        pending = pending[: args.limit]

    print(f"chunks total={len(chunks)} pending={len(pending)} completed={len(completed)}")

    for chunk in pending:
        cid = str(chunk.get("chunk_id"))
        messages = _build_messages(chunk, style=args.style, glossary=glossary)
        last_err = None

        for attempt in range(1, args.max_retries + 1):
            try:
                resp = _call_chat(
                    args.model,
                    messages,
                    auth_profile=args.auth_profile,
                    allow_openrouter_fallback=not args.no_openrouter_fallback,
                )
                text = _extract_text_from_response(resp)
                usage = resp.get("usage") or {}

                rec = {
                    "chunk_id": cid,
                    "order": chunk.get("order"),
                    "book_key": chunk.get("book_key"),
                    "model": _normalize_model(args.model),
                    "source_lang": chunk.get("source_lang"),
                    "target_lang": chunk.get("target_lang"),
                    "translation_text": text,
                    "usage": usage,
                }
                _append_jsonl(out_path, rec)

                completed[cid] = {
                    "at": int(time.time()),
                    "attempts": attempt,
                    "usage": usage,
                }
                if cid in failed:
                    del failed[cid]
                _save_state(state_path, state)
                print(f"ok {cid} ({attempt})")
                break
            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8", errors="ignore")
                except Exception:
                    body = str(e)
                last_err = f"HTTP {e.code}: {body[:400]}"
                if e.code in {429, 500, 502, 503, 504}:
                    time.sleep((args.sleep_ms / 1000.0) * attempt)
                    continue
                break
            except Exception as e:
                last_err = str(e)
                time.sleep((args.sleep_ms / 1000.0) * attempt)

        if cid not in completed:
            failed[cid] = {"at": int(time.time()), "error": last_err or "unknown"}
            _save_state(state_path, state)
            print(f"fail {cid}: {last_err}")

        time.sleep(args.sleep_ms / 1000.0)

    done = len(completed)
    fail = len(failed)
    print(f"done completed={done} failed={fail}")


if __name__ == "__main__":
    main()
