"""
Centralized Prompt Templates for Nano Banana Image Generation
==============================================================
Edit this file to update prompts used across the system.
All image generation prompts reference these templates.
"""

PRODUCT_IMAGE_PROMPT = (
    "Professional e-commerce product photograph of {product_title}: {description}. "
    "Clean white background, studio lighting, 8K quality, commercial product photography. "
    "The product should be centered, well-lit, with realistic shadows and reflections. "
    "No watermarks, no text overlays."
)

TEXT_INSTRUCTIONS = (
    "If the reference image contains any non-English text (e.g. Chinese, Arabic, etc.), "
    "translate it into English and render the translated text neatly on the image. "
    "Position all text with professional marketing layout — centered, well-spaced, "
    "readable fonts, appropriate sizing."
)

REPOSITIONING_NEGATIVE_PROMPT = (
    "chinese text, chinese characters, blurry, watermark, low quality, "
    "distorted proportions, missing parts, extra objects, busy background, "
    "dark background, shadows on product, reflections on product"
)

PRODUCT_MOCKUP_PROMPT = (
    "Professional product photography of {product}. "
    "High-end commercial lighting, {style} presentation. "
    "Background: {background}. Camera angle: {camera_angle}. "
    "Product prominently centered, shallow depth of field, "
    "refined reflections, premium e-commerce quality, 8K detail."
)

LIFESTYLE_PROMPT = (
    "Lifestyle photography of {subject} in a {setting}. "
    "Natural {lighting} lighting, candid moment, {mood} atmosphere. "
    "Style: {style}. Warm and inviting composition. "
    "Shot on professional camera, realistic skin tones, authentic interactions."
)

MARKETING_BANNER_PROMPT = (
    "Professional marketing banner for {campaign}. "
    "Bold {style} design, {color_scheme} color scheme. "
    "Clear focal point: {focal_point}. "
    "Space for text overlay on {text_position}. "
    "High contrast, brand-compliant, conversion-optimized composition."
)

HERO_IMAGE_PROMPT = (
    "Hero product image of {product_title}. "
    "Dramatic studio lighting, premium e-commerce presentation, "
    "pure white background with soft reflections, 8K ultra-detailed, "
    "product perfectly isolated, commercial grade photography."
)

DETAIL_IMAGE_PROMPT = (
    "Close-up detail shot of {product_title}. "
    "Macro photography showing texture and craftsmanship, "
    "soft diffused lighting, shallow depth of field, "
    "premium material details visible, high-end product photography."
)

SMOKE_TEST_PROMPT = (
    "Write a 1-sentence photo description for {product_title}."
)

SMOKE_TEST_SYSTEM = (
    "You are a test assistant. Reply with a short description."
)
