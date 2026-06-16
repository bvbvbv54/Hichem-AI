from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from models.enums import TemplateCategory


@dataclass
class PromptTemplate:
    name: str
    category: TemplateCategory
    description: str
    system_prompt: str
    template: str
    default_parameters: dict[str, Any] = field(default_factory=dict)
    suggested_aspect_ratio: str = "1:1"
    suggested_style: str = "photorealistic"


ECOMMERCE_TEMPLATES: dict[str, PromptTemplate] = {
    "product_mockup": PromptTemplate(
        name="Product Mockup",
        category=TemplateCategory.PRODUCT_MOCKUP,
        description="Professional product mockup images for e-commerce",
        system_prompt=(
            "You are an expert e-commerce product photographer. Create detailed product mockup prompts "
            "that showcase products in professional, appealing ways. Include lighting, angles, and background details."
        ),
        template=(
            "Professional product photography of {product}. "
            "High-end commercial lighting, {style} presentation. "
            "Background: {background}. Camera angle: {camera_angle}. "
            "Product prominently centered, shallow depth of field, "
            "refined reflections, premium e-commerce quality, 8K detail."
        ),
        default_parameters={
            "style": "minimalist",
            "background": "solid white gradient, soft shadows",
            "camera_angle": "slightly elevated 15 degrees",
        },
        suggested_aspect_ratio="1:1",
        suggested_style="photorealistic",
    ),
    "lifestyle": PromptTemplate(
        name="Lifestyle Image",
        category=TemplateCategory.LIFESTYLE,
        description="Lifestyle imagery showing products in use",
        system_prompt=(
            "You are an expert lifestyle photographer. Create authentic, engaging lifestyle "
            "image prompts that show products being used naturally in real-world settings."
        ),
        template=(
            "Lifestyle photography of {subject} in a {setting}. "
            "Natural {lighting} lighting, candid moment, {mood} atmosphere. "
            "Style: {style}. Warm and inviting composition. "
            "Shot on professional camera, realistic skin tones, authentic interactions."
        ),
        default_parameters={
            "setting": "modern living room with natural elements",
            "lighting": "soft window",
            "mood": "warm and cozy",
            "style": "editorial lifestyle photography",
        },
        suggested_aspect_ratio="4:5",
    ),
    "marketing_banner": PromptTemplate(
        name="Marketing Banner",
        category=TemplateCategory.MARKETING_BANNER,
        description="Marketing banner graphics for campaigns",
        system_prompt=(
            "You are an expert graphic designer specializing in marketing banners. "
            "Create visually striking banner prompts optimized for conversion."
        ),
        template=(
            "Professional marketing banner for {campaign}. "
            "Bold {style} design, {color_scheme} color scheme. "
            "Clear focal point: {focal_point}. "
            "Space for text overlay on {text_position}. "
            "High contrast, brand-compliant, conversion-optimized composition."
        ),
        default_parameters={
            "style": "modern corporate",
            "color_scheme": "brand-compliant complementary",
            "focal_point": "centered product or service visualization",
            "text_position": "left side with ample negative space",
        },
        suggested_aspect_ratio="16:9",
    ),
}

CONTENT_TEMPLATES: dict[str, PromptTemplate] = {
    "blog_thumbnail": PromptTemplate(
        name="Blog Thumbnail",
        category=TemplateCategory.BLOG_THUMBNAIL,
        description="Click-worthy blog post thumbnails",
        system_prompt=(
            "You are an expert content creator specializing in blog thumbnails. "
            "Create eye-catching thumbnail prompts that drive clicks."
        ),
        template=(
            "YouTube-style blog thumbnail for topic: {topic}. "
            "Bold {style} design, vibrant {color_scheme} colors. "
            "Central focal point: {focal_point}. "
            "High energy, text overlay space on {text_position}. "
            "Click-worthy composition, sharp details, contrasting elements."
        ),
        default_parameters={
            "style": "modern and clean",
            "color_scheme": "warm and inviting",
            "focal_point": "relevant object or scene",
            "text_position": "bottom third",
        },
        suggested_aspect_ratio="16:9",
    ),
    "instagram_creative": PromptTemplate(
        name="Instagram Creative",
        category=TemplateCategory.INSTAGRAM_CREATIVE,
        description="Instagram feed and story creatives",
        system_prompt=(
            "You are an expert social media content creator specializing in Instagram. "
            "Create scroll-stopping Instagram image prompts optimized for engagement."
        ),
        template=(
            "Instagram {format} creative for brand: {brand}. "
            "Theme: {theme}. Aesthetic: {aesthetic}. "
            "Dominant colors: {colors}. "
            "Stop-scroll composition, {mood} atmosphere. "
            "Professional grade, Insta-worthy, high engagement potential."
        ),
        default_parameters={
            "format": "feed post",
            "brand": "modern lifestyle brand",
            "theme": "minimal luxury",
            "aesthetic": "clean and airy",
            "colors": "neutral tones with pop of color",
            "mood": "aspirational and serene",
        },
        suggested_aspect_ratio="1:1",
    ),
    "linkedin_creative": PromptTemplate(
        name="LinkedIn Creative",
        category=TemplateCategory.LINKEDIN_CREATIVE,
        description="Professional LinkedIn content graphics",
        system_prompt=(
            "You are an expert B2B content creator specializing in LinkedIn. "
            "Create professional, authoritative LinkedIn image prompts."
        ),
        template=(
            "LinkedIn professional graphic for: {topic}. "
            "Corporate {style} aesthetic, {color_scheme} palette. "
            "Professional {mood} atmosphere. "
            "Clean composition, text space on {text_position}. "
            "Trust-building visual, industry authority tone."
        ),
        default_parameters={
            "style": "modern professional",
            "color_scheme": "professional blue and white",
            "mood": "confident and innovative",
            "text_position": "right side",
        },
        suggested_aspect_ratio="1.91:1",
    ),
    "youtube_thumbnail": PromptTemplate(
        name="YouTube Thumbnail",
        category=TemplateCategory.YOUTUBE_THUMBNAIL,
        description="High-CTR YouTube video thumbnails",
        system_prompt=(
            "You are an expert YouTube thumbnail designer. "
            "Create high-click-through-rate thumbnail prompts optimized for the YouTube algorithm."
        ),
        template=(
            "YouTube thumbnail for video: {video_topic}. "
            "Ultra-bold {style} design, high saturation {color_scheme}. "
            "Express focal subject: {focal_subject}. "
            "Dramatic {lighting}, intense {mood} vibe. "
            "Space for big text overlay on {text_position}. "
            "Curiosity-gap composition, sharp contrast."
        ),
        default_parameters={
            "style": "aggressive and eye-catching",
            "color_scheme": "high contrast warm and cool",
            "focal_subject": "surprised or dramatic expression",
            "lighting": "dramatic side lighting",
            "mood": "intriguing and urgent",
            "text_position": "bottom center",
        },
        suggested_aspect_ratio="16:9",
    ),
}

SAAS_TEMPLATES: dict[str, PromptTemplate] = {
    "landing_page": PromptTemplate(
        name="Landing Page Graphic",
        category=TemplateCategory.LANDING_PAGE,
        description="Hero graphics for landing pages",
        system_prompt=(
            "You are an expert SaaS designer specializing in landing page hero graphics. "
            "Create modern, conversion-focused hero section imagery."
        ),
        template=(
            "SaaS landing page hero graphic for: {product}. "
            "{style} design language, {color_scheme} gradient. "
            "Abstract visualization of {concept}. "
            "Clean, minimal, professional. "
            "Space for headline on {text_position}. "
            "Modern SaaS aesthetic, high-end tech feel."
        ),
        default_parameters={
            "style": "modern flat design with 3D elements",
            "color_scheme": "purple to blue gradient",
            "concept": "digital transformation and connectivity",
            "text_position": "left side with floating elements on right",
        },
        suggested_aspect_ratio="16:9",
    ),
    "feature_illustration": PromptTemplate(
        name="Feature Illustration",
        category=TemplateCategory.FEATURE_ILLUSTRATION,
        description="Feature showcase illustrations",
        system_prompt=(
            "You are an expert SaaS illustrator. Create clear, compelling feature illustrations "
            "that explain product capabilities visually."
        ),
        template=(
            "Feature illustration for: {feature_name}. "
            "Isometric {style} view, {color_scheme} color scheme. "
            "Shows: {what_it_does}. "
            "User interface mockup integrated, {mood} atmosphere. "
            "Clean {background}, professional SaaS aesthetic."
        ),
        default_parameters={
            "style": "3D isometric",
            "color_scheme": "brand colors with white space",
            "what_it_does": "the main functionality in action",
            "mood": "efficient and productive",
            "background": "gradient subtle background",
        },
        suggested_aspect_ratio="4:3",
    ),
    "marketing_asset": PromptTemplate(
        name="Marketing Asset",
        category=TemplateCategory.MARKETING_ASSET,
        description="General marketing and social proof assets",
        system_prompt=(
            "You are an expert SaaS marketing designer. Create versatile marketing assets "
            "for campaigns, social proof, and promotional materials."
        ),
        template=(
            "SaaS marketing asset for: {campaign}. "
            "{style} design, {color_scheme} branding. "
            "Theme: {theme}. Showcases: {showcase}. "
            "Professional marketing quality, brand-consistent, "
            "conversion-optimized composition."
        ),
        default_parameters={
            "style": "modern tech",
            "color_scheme": "brand-compliant",
            "theme": "innovation and growth",
            "showcase": "product benefits and key features",
        },
        suggested_aspect_ratio="16:9",
    ),
}

ALL_TEMPLATES: dict[str, PromptTemplate] = {}
ALL_TEMPLATES.update(ECOMMERCE_TEMPLATES)
ALL_TEMPLATES.update(CONTENT_TEMPLATES)
ALL_TEMPLATES.update(SAAS_TEMPLATES)


def get_template(name: str) -> Optional[PromptTemplate]:
    return ALL_TEMPLATES.get(name)


def list_templates(category: Optional[str] = None) -> list[dict[str, Any]]:
    result = []
    for name, tpl in ALL_TEMPLATES.items():
        if category and tpl.category.value != category:
            continue
        result.append({
            "name": name,
            "category": tpl.category.value,
            "description": tpl.description,
            "default_parameters": tpl.default_parameters,
            "suggested_aspect_ratio": tpl.suggested_aspect_ratio,
            "suggested_style": tpl.suggested_style,
        })
    return result
