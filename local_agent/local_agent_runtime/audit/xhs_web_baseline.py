from __future__ import annotations

from typing import Any

from local_agent_runtime.connectors.xhs.homefeed_probe import CARD_EXTRACTION_SCRIPT


async def extract_homefeed_web_baseline(page, limit: int) -> list[dict[str, Any]]:
    return (await page.evaluate(CARD_EXTRACTION_SCRIPT))[:limit]


async def extract_search_web_baseline(page, limit: int) -> list[dict[str, Any]]:
    return (await page.evaluate(CARD_EXTRACTION_SCRIPT))[:limit]


async def extract_detail_web_baseline(page) -> dict[str, Any]:
    return await page.evaluate(
        """
        () => {
          const textOf = (selector) => {
            const node = document.querySelector(selector);
            return node ? (node.innerText || node.textContent || '').trim() : null;
          };
          const imgs = Array.from(document.querySelectorAll('img')).map(img => img.currentSrc || img.src).filter(Boolean);
          const video = document.querySelector('video');
          return {
            title: textOf('#detail-title, .title, [class*="title"]'),
            body_text: textOf('#detail-desc, .desc, [class*="desc"], [class*="content"]'),
            author: textOf('.author, [class*="author"], .username, [class*="user"]'),
            like_count: textOf('[class*="like"], [class*="interact"]'),
            comment_count: textOf('[class*="comment"]'),
            collect_count: textOf('[class*="collect"]'),
            share_count: textOf('[class*="share"]'),
            image_count: imgs.length,
            has_video: !!video
          };
        }
        """
    )


async def extract_comment_web_baseline(page, limit: int) -> list[dict[str, Any]]:
    return await page.evaluate(
        """
        (limit) => Array.from(document.querySelectorAll('[class*="comment"], .comment-item, [data-comment-id]')).slice(0, limit).map(node => {
          const author = node.querySelector('[class*="author"], [class*="name"], a[href*="/user/profile"]');
          const like = node.querySelector('[class*="like"], [class*="count"]');
          return {
            body_text: (node.innerText || node.textContent || '').trim().slice(0, 500),
            author_name: author ? (author.innerText || author.textContent || '').trim() : null,
            like_count: like ? (like.innerText || like.textContent || '').trim() : null
          };
        })
        """,
        limit,
    )


async def extract_creator_web_baseline(page, limit: int) -> dict[str, Any]:
    cards = (await page.evaluate(CARD_EXTRACTION_SCRIPT))[:limit]
    profile = await page.evaluate(
        """
        () => {
          const textOf = (selector) => {
            const node = document.querySelector(selector);
            return node ? (node.innerText || node.textContent || '').trim() : null;
          };
          return {
            nickname: textOf('.user-name, .username, [class*="user-name"], [class*="name"]'),
            bio: textOf('[class*="desc"], [class*="bio"], [class*="profile"]'),
            counters_text: document.body ? (document.body.innerText || '').slice(0, 2000) : ''
          };
        }
        """
    )
    return {"profile": profile, "cards": cards}
