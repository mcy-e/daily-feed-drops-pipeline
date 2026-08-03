"""Config-driven Manim scene for a single content segment."""

import json
import os

from manim import *

from scripts.constants import CONTENT_STYLE_PRESETS, MANIM_FRAME_WIDTH, MANIM_FRAME_HEIGHT

config.frame_width = MANIM_FRAME_WIDTH
config.frame_height = MANIM_FRAME_HEIGHT


def _load_config() -> dict:
    config_path = os.environ.get("CONTENT_SEGMENT_CONFIG")
    if not config_path:
        raise RuntimeError("CONTENT_SEGMENT_CONFIG env var not set")
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _hex_to_manim(hex_color: str):
    return ManimColor(hex_color)


class SegmentScene(Scene):
    def construct(self):
        seg_config = _load_config()
        segment = seg_config["segment"]
        content_type = seg_config["content_type"]
        duration = seg_config["duration"]
        style = CONTENT_STYLE_PRESETS.get(content_type, CONTENT_STYLE_PRESETS["explained_topic"])

        self.camera.background_color = _hex_to_manim(style["bg_color"])

        if content_type == "motivation_content":
            gradient = Rectangle(
                width=config.frame_width, height=config.frame_height,
                fill_color=[_hex_to_manim("#3d2817"), _hex_to_manim("#c8791a")],
                fill_opacity=1, stroke_width=0,
            )
            self.add(gradient)

        if content_type == "viral_news":
            ticker = Rectangle(
                width=config.frame_width, height=0.6,
                fill_color=_hex_to_manim(style["accent_color"]),
                fill_opacity=1, stroke_width=0,
            ).to_edge(UP, buff=0)
            breaking = Text(
                "BREAKING", font=style["font"], color="#ffffff",
                font_size=28, weight=BOLD,
            ).move_to(ticker)
            self.add(ticker, breaking)

        visual_type = segment.get("visual_type", "text")
        visual_content = segment.get("visual_content", "")
        font = style["font"]
        text_color = style["text_color"]
        accent = style["accent_color"]

        mobjects = self._build_visual(
            visual_type, visual_content, segment, font, text_color, accent, content_type
        )

        anim_time = min(1.5, duration * 0.4)
        wait_time = max(0.1, duration - anim_time)

        if isinstance(mobjects, list):
            for mobj in mobjects:
                self.play(FadeIn(mobj, run_time=anim_time / len(mobjects)), rate_func=smooth)
        else:
            if content_type == "motivation_content":
                self.play(FadeIn(mobjects, shift=UP * 0.3, run_time=anim_time), rate_func=smooth)
            elif content_type == "quiz_riddle":
                self.play(GrowFromCenter(mobjects, run_time=anim_time), rate_func=smooth)
            elif content_type == "viral_news":
                self.play(FadeIn(mobjects, shift=DOWN * 0.2, run_time=anim_time), rate_func=smooth)
            else:
                self.play(FadeIn(mobjects, run_time=anim_time), rate_func=smooth)

        self.wait(wait_time)

    def _build_visual(
        self, visual_type, visual_content, segment, font, text_color, accent, content_type
    ):
        if visual_type == "image" and segment.get("image_path"):
            return self._build_image(segment["image_path"], content_type)

        if visual_type == "number":
            stat_text = Text(
                str(visual_content), font=font, color=accent,
                font_size=96, weight=BOLD,
            )
            if content_type == "football_trivia":
                card = RoundedRectangle(
                    corner_radius=0.2, width=max(stat_text.width + 1.2, 5),
                    height=stat_text.height + 1.0,
                    fill_color=_hex_to_manim("#ffffff"), fill_opacity=0.08,
                    stroke_color=_hex_to_manim(accent), stroke_width=3,
                )
                stat_text.move_to(card.get_center())
                return VGroup(card, stat_text)
            return stat_text

        if visual_type == "list":
            if isinstance(visual_content, list):
                items = [str(i) for i in visual_content]
            else:
                items = visual_content.split("\n") if "\n" in visual_content else visual_content.split("|")
            items = [i.strip().lstrip("•- ") for i in items if i.strip()]
            texts = [Text(f"• {item}", font=font, color=text_color, font_size=36) for item in items]
            group = VGroup(*texts).arrange(DOWN, aligned_edge=LEFT, buff=0.4)
            if group.width > 8:
                group.scale_to_fit_width(8)
            return group

        if visual_type == "shape":
            label = Text(visual_content, font=font, color=text_color, font_size=42)
            shape = Circle(radius=2, color=accent, fill_opacity=0.15, stroke_width=3)
            if content_type == "quiz_riddle":
                shape = Text("?", font=font, color=accent, font_size=120, weight=BOLD)
                return VGroup(shape, label.next_to(shape, DOWN, buff=0.5))
            return VGroup(shape, label.move_to(shape.get_center()))

        # Default: text
        font_size = 52 if content_type == "kids_content" else 48
        if content_type == "viral_news":
            font_size = 36
        text = Text(
            visual_content, font=font, color=text_color,
            font_size=font_size,
            weight=BOLD if content_type in ("viral_news", "kids_content") else NORMAL,
        )
        if text.width > 8:
            text.scale_to_fit_width(8)
        if content_type == "motivation_content":
            text.set_color(text_color)
        return text

    def _build_image(self, image_path, content_type):
        img = ImageMobject(image_path)
        if content_type == "meme_recap":
            img.scale_to_fit_height(config.frame_height)
            if img.width > config.frame_width:
                img.scale_to_fit_width(config.frame_width)
        else:
            img.scale_to_fit_width(config.frame_width * 0.9)
        return img
