import anthropic
import httpx
import random
import logging
import urllib.parse
import config

logger = logging.getLogger(__name__)

# Темы для постов — чередуются рандомно
CRYPTO_TOPICS = [
    "Bitcoin price analysis and market sentiment today",
    "Ethereum ecosystem news and DeFi updates",
    "Altcoin season signals and portfolio strategy",
    "On-chain metrics that signal bull or bear market",
    "Common crypto trading mistakes beginners make",
    "Crypto market fear and greed index explained",
    "Layer 2 solutions and why they matter",
    "Stablecoin yields and passive income in crypto",
    "NFT market current state and future outlook",
    "Crypto regulation news and its market impact",
    "Memecoin culture and how to approach them safely",
    "Bitcoin halving effects on the market cycle",
]

POST_SYSTEM_PROMPT = """You are a sharp, engaging crypto content creator for Threads (Instagram's platform).
Write posts that feel authentic — not corporate, not hype. Mix insight with personality.

Rules:
- Max 400 characters (Threads limit is 500 but keep it punchy)
- Use 2-3 relevant emojis naturally, not at the end of every line
- No hashtags — they look spammy on Threads
- End with a question or provocative statement to drive comments
- Write in English
- Be opinionated, not neutral — people engage with takes
- No "GM" or cringe crypto slang
"""

IMAGE_SYSTEM_PROMPT = """Generate a concise image prompt for an AI image generator.
The image should be: dark/moody tech aesthetic, crypto/finance themed, no text in image.
Style: cinematic, 16:9, photorealistic or stylized digital art.
Return ONLY the prompt, nothing else. Max 50 words."""


async def generate_crypto_post() -> tuple[str, str]:
    """Returns (post_text, image_url)"""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    topic = random.choice(CRYPTO_TOPICS)
    logger.info(f"Generating post about: {topic}")

    # 1. Generate post text
    text_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=300,
        system=POST_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Write a Threads post about: {topic}"}],
    )
    post_text = text_response.content[0].text.strip()

    # 2. Generate image prompt
    img_prompt_response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=100,
        system=IMAGE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": f"Topic: {topic}\nPost text: {post_text}"}],
    )
    image_prompt = img_prompt_response.content[0].text.strip()

    # 3. Get image from Pollinations.ai (free, no API key needed)
    encoded_prompt = urllib.parse.quote(image_prompt)
    seed = random.randint(1, 99999)
    image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1280&height=720&seed={seed}&nologo=true"

    # Verify image is accessible
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.head(image_url)
        if resp.status_code != 200:
            logger.warning("Image generation failed, posting text only")
            return post_text, None

    logger.info(f"Generated post ({len(post_text)} chars) + image")
    return post_text, image_url
