# src/utils/utf8_guard.py
from __future__ import annotations
import discord
from typing import Any

def _utf8_clean(s: str | None) -> str | None:
    if not isinstance(s, str) or not s:
        return s
    s = s.replace("\u00A0", " ")
    if all(ord(ch) < 128 for ch in s):
        return s
    markers = ("Ã", "Â", "â", "ð", "€", "™", "œ", "š", "ž")
    if not any(m in s for m in markers):
        return s
    for enc in ("cp1252", "latin1"):
        try:
            fixed = s.encode(enc, "strict").decode("utf-8")
            if any(m in fixed for m in markers):
                try:
                    fixed2 = fixed.encode(enc, "strict").decode("utf-8")
                    return fixed2
                except Exception:
                    return fixed
            return fixed
        except Exception:
            continue
    return s

def _clean_embed(e: discord.Embed | None):
    if not isinstance(e, discord.Embed):
        return
    if e.title:        e.title        = _utf8_clean(e.title)
    if e.description:  e.description  = _utf8_clean(e.description)
    if e.footer and e.footer.text is not None:
        e.set_footer(text=_utf8_clean(e.footer.text), icon_url=e.footer.icon_url)
    if e.author and e.author.name is not None:
        e.set_author(name=_utf8_clean(e.author.name), url=e.author.url, icon_url=e.author.icon_url)
    for i, f in enumerate(list(e.fields or [])):
        e.set_field_at(i, name=_utf8_clean(f.name), value=_utf8_clean(f.value), inline=f.inline)

def _clean_view(view: discord.ui.View | None):
    if not view: return
    for child in view.children:
        if hasattr(child, "label") and isinstance(child.label, str):
            child.label = _utf8_clean(child.label)
        if hasattr(child, "placeholder") and isinstance(child.placeholder, str):
            child.placeholder = _utf8_clean(child.placeholder)

def _ckw(kwargs: dict[str, Any]) -> dict[str, Any]:
    k = dict(kwargs)
    if isinstance(k.get("content"), str):
        k["content"] = _utf8_clean(k["content"])
    if "embed" in k:   _clean_embed(k["embed"])
    if "embeds" in k and k["embeds"]:
        for e in k["embeds"]: _clean_embed(e)
    if "view" in k:    _clean_view(k["view"])
    for key in ("username", "thread_name"):
        if isinstance(k.get(key), str):
            k[key] = _utf8_clean(k[key])
    return k

def install_utf8_guard(logger=None):
    # Send
    _orig_send = discord.abc.Messageable.send
    async def _send(self, *a, **kw): return await _orig_send(self, *a, **_ckw(kw))
    discord.abc.Messageable.send = _send

    # Interaction response send/edit
    _orig_irs = discord.InteractionResponse.send_message
    async def _irs(self, *a, **kw): return await _orig_irs(self, *a, **_ckw(kw))
    discord.InteractionResponse.send_message = _irs

    _orig_ire = discord.InteractionResponse.edit_message
    async def _ire(self, *a, **kw): return await _orig_ire(self, *a, **_ckw(kw))
    discord.InteractionResponse.edit_message = _ire

    # Followups / webhooks
    _orig_whs = discord.Webhook.send
    async def _whs(self, *a, **kw): return await _orig_whs(self, *a, **_ckw(kw))
    discord.Webhook.send = _whs

    # Message.edit (regular edits)
    _orig_me = discord.Message.edit
    async def _me(self, *a, **kw): return await _orig_me(self, *a, **_ckw(kw))
    discord.Message.edit = _me

    if logger:
        logger.info("utf8 deep-guard installed")
