"""短视频脚本 — 生成(口播稿+分镜头) + CRUD"""

import json
import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.llm import call_llm_with_retry, clean_response, create_llm
from app.copywriting.models import VideoScript
from app.core.logging import logger
from app.retrieval.fusion import hybrid_retrieve


def parse_storyboard(storyboard: str | None) -> list[dict]:
    """解析分镜头文本（每行 序号|画面|台词|时长）为结构化列表。"""
    if not storyboard:
        return []
    shots: list[dict] = []
    for line in storyboard.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in re.split(r"[|｜]", line)]
        shots.append({
            "no": parts[0] if len(parts) > 0 else "",
            "scene": parts[1] if len(parts) > 1 else "",
            "line": parts[2] if len(parts) > 2 else "",
            "dur": parts[3] if len(parts) > 3 else "",
        })
    return shots


def build_script_body(script: VideoScript, table: bool = True) -> str:
    """将脚本渲染为导出正文（不含标题），供 md/html/docx 导出使用。

    table=True 时分镜头用 Markdown 表格；table=False 用易读的逐行列表（适合 DOCX/TXT）。
    """
    parts: list[str] = []
    meta: list[str] = []
    if script.hot_word:
        meta.append(f"**关联热点：**{script.hot_word}")
    if script.hot_url:
        meta.append(f"**原视频链接：**{script.hot_url}")
    if meta:
        parts.append("\n".join(meta))

    parts.append("## 口播稿")
    parts.append(script.voiceover or "（无）")

    parts.append("## 分镜头脚本")
    shots = parse_storyboard(script.storyboard)
    if shots:
        if table:
            rows = ["| 镜头 | 画面描述 | 台词口播 | 时长(秒) |", "|---|---|---|---|"]
            for s in shots:
                rows.append(f"| {s['no']} | {s['scene']} | {s['line']} | {s['dur']} |")
            parts.append("\n".join(rows))
        else:
            lines: list[str] = []
            for s in shots:
                line = f"镜头 {s['no'] or '?'}"
                if s["scene"]:
                    line += f"：画面：{s['scene']}"
                if s["line"]:
                    line += f"｜台词：{s['line']}"
                if s["dur"]:
                    line += f"｜时长：{s['dur']}秒"
                lines.append(line)
            parts.append("\n".join(lines))
    else:
        parts.append(script.storyboard or "（无）")

    if script.requirement:
        parts.append(f"## AI 要求\n{script.requirement}")
    if script.material_notes:
        parts.append(f"## 素材摘要\n{script.material_notes}")

    return "\n\n".join(parts)


def build_script_pdf(script: VideoScript) -> bytes:
    """将脚本渲染为 PDF（中文 STSong-Light 内置字体，无需外部字体文件）。"""
    from io import BytesIO

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Table,
        TableStyle,
    )
    from xml.sax.saxutils import escape

    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))

    title_style = ParagraphStyle("title", fontName="STSong-Light", fontSize=18, leading=26, alignment=1, spaceAfter=10)
    meta_style = ParagraphStyle("meta", fontName="STSong-Light", fontSize=9, leading=14, textColor=colors.grey, spaceAfter=3)
    h2_style = ParagraphStyle("h2", fontName="STSong-Light", fontSize=13, leading=18, spaceBefore=12, spaceAfter=6)
    body_style = ParagraphStyle("body", fontName="STSong-Light", fontSize=11, leading=18)
    cell_style = ParagraphStyle("cell", fontName="STSong-Light", fontSize=9, leading=13)
    head_style = ParagraphStyle("head", fontName="STSong-Light", fontSize=9.5, leading=13)

    def esc(text: str) -> str:
        return escape(text or "").replace("\n", "<br/>")

    story: list = []
    story.append(Paragraph(esc(script.title), title_style))
    if script.hot_word:
        story.append(Paragraph(f"关联热点：{esc(script.hot_word)}", meta_style))
    if script.hot_url:
        story.append(Paragraph(f"原视频链接：{esc(script.hot_url)}", meta_style))

    story.append(Paragraph("口播稿", h2_style))
    story.append(Paragraph(esc(script.voiceover), body_style))

    story.append(Paragraph("分镜头脚本", h2_style))
    shots = parse_storyboard(script.storyboard)
    if shots:
        rows = [[Paragraph(h, head_style) for h in ("镜头", "画面描述", "台词口播", "时长(秒)")]]
        for s in shots:
            rows.append([
                Paragraph(esc(s["no"] or " "), cell_style),
                Paragraph(esc(s["scene"] or " "), cell_style),
                Paragraph(esc(s["line"] or " "), cell_style),
                Paragraph(esc(s["dur"] or " "), cell_style),
            ])
        table = Table(rows, colWidths=[2.2 * cm, 5.4 * cm, 6.4 * cm, 2.0 * cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
    else:
        story.append(Paragraph(esc(script.storyboard), body_style))

    if script.requirement:
        story.append(Paragraph("AI 要求", h2_style))
        story.append(Paragraph(esc(script.requirement), body_style))
    if script.material_notes:
        story.append(Paragraph("素材摘要", h2_style))
        story.append(Paragraph(esc(script.material_notes), body_style))

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2 * cm, rightMargin=2 * cm,
    )
    doc.build(story)
    return buf.getvalue()


_SCRIPT_PROMPT = """你是短视频编导，为以下选题创作短视频脚本。

选题：
- 标题：{title}
- 关联热点：{hot_word}（原视频链接：{hot_url}）

参考知识（来自企业知识库，提供事实依据，不要直接照抄）：
{knowledge}

素材说明：
{materials}

用户创作要求：
{requirement}

请同时产出两种脚本，直接返回 JSON（不要其他文字）：
{{
  "voiceover": "口播稿全文：一段式流畅口播，包含开场钩子(3-5秒内抓住观众)、主体内容、结尾行动号召/互动引导，语气适合短视频",
  "storyboard": "分镜头脚本：每行一个镜头，格式【序号|画面描述|台词口播|时长秒】，4-8 个镜头，覆盖开场钩子到结尾"
}}

要求：
- 口播稿与分镜头台词一致
- 结合知识库事实，不要编造专业数据
- 字幕/口播自然口语化"""


class ScriptService:
    """短视频脚本服务"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ============================================================
    # 生成
    # ============================================================

    async def generate_script(
        self,
        user_id: int,
        title: str,
        hot_word: str | None = None,
        hot_url: str | None = None,
        requirement: str = "",
        material_notes: str = "",
    ) -> dict:
        """检索知识库 → LLM 生成口播稿 + 分镜头脚本。"""
        knowledge = await self._retrieve_knowledge(title)

        prompt = _SCRIPT_PROMPT.format(
            title=title,
            hot_word=hot_word or "（无）",
            hot_url=hot_url or "（无）",
            knowledge=knowledge or "（知识库暂无相关内容）",
            materials=material_notes or "（无素材）",
            requirement=requirement.strip() or "（无额外要求，按热点自然发挥）",
        )

        llm = create_llm(temperature=0.6, max_tokens=3200, top_p=0.9)
        raw = await call_llm_with_retry(
            llm, [{"role": "user", "content": prompt}], max_retries=2, clean=True
        )

        voiceover, storyboard = self._parse_script(raw, title)

        return {
            "title": title,
            "hot_word": hot_word,
            "hot_url": hot_url,
            "voiceover": voiceover,
            "storyboard": storyboard,
            "material_notes": material_notes or None,
            "requirement": requirement.strip() or None,
            "user_id": user_id,
        }

    @staticmethod
    async def _retrieve_knowledge(title: str) -> str:
        """按标题检索知识库，返回拼接文本。"""
        try:
            retrieved = await hybrid_retrieve(title, scope="public", top_k=6)
        except Exception as exc:
            logger.warning("copy_script_retrieve_failed", error=str(exc))
            return ""
        parts = [clean_response(r.content) for r in retrieved[:6]]
        return "\n\n---\n\n".join(parts)

    @staticmethod
    def _parse_script(raw: str, fallback_title: str) -> tuple[str, str]:
        """从 LLM 输出解析 (voiceover, storyboard)。失败时返回空。"""
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                voiceover = str(data.get("voiceover", "")).strip()
                storyboard = ScriptService._normalize_storyboard(data.get("storyboard"))
                return voiceover, storyboard
        except Exception:
            pass
        # 兜底：无 JSON 时尝试按分隔解析
        lines = [ln for ln in raw.splitlines() if ln.strip()]
        voiceover = ""
        storyboard = None
        if lines:
            story_parts: list[str] = []
            voice_parts: list[str] = []
            for ln in lines:
                if re.match(r"^\s*\d+\s*[|｜]", ln):
                    story_parts.append(ln.strip())
                else:
                    voice_parts.append(ln.strip())
            voiceover = "\n".join(voice_parts)
            if story_parts:
                storyboard = "\n".join(story_parts)
        if not voiceover:
            voiceover = f"（脚本生成失败，请重试：{fallback_title}）"
        return voiceover, storyboard

    @staticmethod
    def _normalize_storyboard(storyboard) -> str | None:
        """把 LLM 返回的分镜头统一为行格式：序号|画面描述|台词口播|时长秒。

        兼容：字符串（已是行格式）、dict 列表、dict（单个镜头）。
        """
        if storyboard is None:
            return None
        if isinstance(storyboard, str):
            return storyboard.strip() or None
        if isinstance(storyboard, dict):
            storyboard = [storyboard]
        if isinstance(storyboard, list):
            lines: list[str] = []
            for i, shot in enumerate(storyboard, 1):
                if isinstance(shot, dict):
                    def _pick(*keys: str, _shot: dict = shot) -> str:
                        for k in keys:
                            v = _shot.get(k)
                            if v is not None and str(v).strip():
                                return str(v).strip()
                        return ""
                    num = _pick("序号", "镜头", "no", "index") or str(i)
                    scene = _pick("画面", "画面描述", "场景", "scene")
                    line = _pick("台词", "台词口播", "口播", "content", "text")
                    dur = _pick("时长", "时长秒", "duration", "seconds") or ""
                    lines.append(f"{num}|{scene}|{line}|{dur}")
                elif isinstance(shot, str) and shot.strip():
                    lines.append(shot.strip())
            if lines:
                return "\n".join(lines)
        return None

    # ============================================================
    # CRUD
    # ============================================================

    async def create_script(self, data: dict) -> VideoScript:
        obj = VideoScript(
            user_id=data["user_id"],
            title=data["title"],
            hot_word=data.get("hot_word"),
            hot_url=data.get("hot_url"),
            voiceover=data.get("voiceover", ""),
            storyboard=data.get("storyboard"),
            material_notes=data.get("material_notes"),
            requirement=data.get("requirement"),
            status="draft",
        )
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        logger.info("video_script_created", script_id=obj.id, title=obj.title)
        return obj

    async def list_scripts(
        self, user_id: int | None, page: int = 1, page_size: int = 20
    ) -> tuple[list[VideoScript], int]:
        base = select(VideoScript)
        count_q = select(func.count(VideoScript.id))
        if user_id is not None:
            base = base.where(VideoScript.user_id == user_id)
            count_q = count_q.where(VideoScript.user_id == user_id)
        base = base.order_by(VideoScript.id.desc()).offset((page - 1) * page_size).limit(page_size)
        total = (await self.db.execute(count_q)).scalar() or 0
        rows = (await self.db.execute(base)).scalars().all()
        return list(rows), total

    async def get_script(self, script_id: int) -> VideoScript | None:
        return await self.db.get(VideoScript, script_id)

    async def update_script(self, script_id: int, data: dict) -> VideoScript | None:
        obj = await self.get_script(script_id)
        if not obj:
            return None
        for field in ("title", "hot_word", "hot_url", "voiceover", "storyboard",
                      "material_notes", "requirement", "status"):
            if field in data and data[field] is not None:
                setattr(obj, field, data[field])
        await self.db.commit()
        await self.db.refresh(obj)
        logger.info("video_script_updated", script_id=script_id)
        return obj

    async def delete_script(self, script_id: int, user_id: int) -> bool:
        obj = await self.get_script(script_id)
        if not obj:
            return False
        if obj.user_id != user_id:
            return False
        await self.db.delete(obj)
        await self.db.commit()
        logger.info("video_script_deleted", script_id=script_id)
        return True
