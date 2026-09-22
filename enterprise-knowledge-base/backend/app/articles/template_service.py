"""写作模板 — CRUD 服务 + 预设种子数据（含按目标账号类型分流）

模板分为两类：
- 通用预设模板（account_type=NULL）：结构/风格，任何人群可用
- 人群预设模板（account_type=user/designer/dealer）：每种目标账号类型固定一套
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.articles.models import WritingTemplate
from app.core.logging import logger

# ============================================================
# 目标账号类型
# ============================================================

ACCOUNT_TYPES: dict[str, str] = {
    "user": "用户",
    "designer": "设计师",
    "dealer": "经销商",
}

# 各人群预设模板的角度提示（供 LLM 角度规划使用）
ACCOUNT_ANGLE_HINTS: dict[str, str] = {
    "user": (
        "面向普通业主/用户人群，文章角度应从用户视角出发：选购指南、常见问题解答、"
        "真实案例分享、避坑指南、效果对比。语言通俗，突出实用价值。"
    ),
    "designer": (
        "面向建筑/设计专业人士，文章角度应从专业视角出发：技术原理解析、方案选型对比、"
        "规范标准解读、设计与施工要点、工程案例分析。专业严谨，突出技术深度。"
    ),
    "dealer": (
        "面向经销商/渠道经营者，文章角度应从商业视角出发：招商政策解读、市场机遇分析、"
        "利润与投入分析、合作模式与支持、成功案例与经营指南。突出商机与合作价值。"
    ),
}

# ============================================================
# 通用预设模板
# ============================================================

PRESET_TEMPLATES = [
    # 结构模板
    {
        "name": "问题解决型",
        "type": "structure",
        "sort_order": 1,
        "prompt_instruction": (
            "请按以下结构组织文章：\n"
            "1. 开头：描述用户痛点，引出核心问题\n"
            "2. 分析：剖析问题产生的深层原因\n"
            "3. 方案：给出具体可行的解决步骤（2-3 条）\n"
            "4. 案例：用真实场景佐证方案的有效性\n"
            "5. 结尾：总结核心观点并给出行动建议"
        ),
    },
    {
        "name": "对比评测型",
        "type": "structure",
        "sort_order": 2,
        "prompt_instruction": (
            "请按以下结构组织文章：\n"
            "1. 开头：介绍背景和对比对象\n"
            "2. 维度一：技术原理对比\n"
            "3. 维度二：实施效果对比\n"
            "4. 维度三：成本投入对比\n"
            "5. 总结：适用场景和选购建议"
        ),
    },
    {
        "name": "教程指南型",
        "type": "structure",
        "sort_order": 3,
        "prompt_instruction": (
            "请按以下结构组织文章：\n"
            "1. 前置知识：读者需要了解的基础概念\n"
            "2. 步骤一：第一阶段的详细操作\n"
            "3. 步骤二：第二阶段的详细操作\n"
            "4. 注意事项：常见误区和避坑指南\n"
            "5. 总结：核心要点回顾"
        ),
    },
    {
        "name": "清单盘点型",
        "type": "structure",
        "sort_order": 4,
        "prompt_instruction": (
            "请按以下结构组织文章：\n"
            "1. 开头：点题并概述本文盘点的范围\n"
            "2. 要点 1：第一个关键点（标题 + 详述 + 小贴士）\n"
            "3. 要点 2：第二个关键点（标题 + 详述 + 小贴士）\n"
            "4. 要点 3：第三个关键点（标题 + 详述 + 小贴士）\n"
            "5. 要点 4：第四个关键点（标题 + 详述 + 小贴士）\n"
            "6. 总结：关键要点速览表"
        ),
    },
    # 风格模板
    {
        "name": "专业权威",
        "type": "style",
        "sort_order": 5,
        "prompt_instruction": (
            "语气风格要求：\n"
            "- 使用准确的专业术语\n"
            "- 引用具体数据和事实支撑观点\n"
            "- 保持客观、严谨、逻辑严密\n"
            "- 避免口语化和主观表达"
        ),
    },
    {
        "name": "轻松口语",
        "type": "style",
        "sort_order": 6,
        "prompt_instruction": (
            "语气风格要求：\n"
            "- 使用短句和日常用语\n"
            "- 多用生动比喻帮助理解\n"
            "- 像和朋友聊天一样亲切自然\n"
            "- 避免过度专业术语"
        ),
    },
    {
        "name": "营销转化",
        "type": "style",
        "sort_order": 7,
        "prompt_instruction": (
            "语气风格要求：\n"
            "- 先制造痛点共鸣（用户为什么需要）\n"
            "- 展示解决方案的独特价值\n"
            "- 量化收益和效果\n"
            "- 结尾给出明确的行动号召"
        ),
    },
    {
        "name": "故事叙事",
        "type": "style",
        "sort_order": 8,
        "prompt_instruction": (
            "语气风格要求：\n"
            "- 以真实场景或人物视角开头\n"
            "- 通过冲突和解决过程推动内容\n"
            "- 融入情感共鸣\n"
            "- 在故事结尾点出核心观点"
        ),
    },
]

# ============================================================
# 人群预设模板 — 每种目标账号类型固定一套
# ============================================================

ACCOUNT_PRESET_TEMPLATES: dict[str, list[dict]] = {
    "user": [
        {
            "name": "选购指南型（用户）",
            "type": "structure",
            "sort_order": 11,
            "prompt_instruction": (
                "请按以下结构组织文章，面向普通业主/用户，语言通俗易懂：\n"
                "1. 开头：从生活痛点引入（如地下室潮湿发霉），引发共鸣\n"
                "2. 判断标准：教用户判断自己是否需要该产品/服务（什么情况用得上）\n"
                "3. 选购要点：给出 2-3 条简单清晰的选购/判断要点\n"
                "4. 使用效果：用通俗语言说明能达到的效果与注意事项\n"
                "5. 结尾：给普通用户可执行的下一步建议"
            ),
        },
        {
            "name": "常见问题解答型（用户）",
            "type": "structure",
            "sort_order": 12,
            "prompt_instruction": (
                "请按以下结构组织文章，面向普通用户：\n"
                "1. 开头：说明本文集中解答用户最关心的几个问题\n"
                "2. 问题 1-3：每个问题一问一答，回答直白不含糊，多用生活化比喻\n"
                "3. 避坑提醒：列出用户容易踩的坑\n"
                "4. 结尾：总结并引导用户进一步咨询"
            ),
        },
        {
            "name": "通俗易懂（用户）",
            "type": "style",
            "sort_order": 13,
            "prompt_instruction": (
                "语气风格要求（面向普通业主/用户）：\n"
                "- 全程少用专业术语，必须用时用生活化语言解释\n"
                "- 多用比喻和类比帮助理解\n"
                "- 短句为主，段落不宜过长\n"
                "- 站在业主/普通用户视角，语气亲切可信"
            ),
        },
    ],
    "designer": [
        {
            "name": "技术原理解析型（设计师）",
            "type": "structure",
            "sort_order": 21,
            "prompt_instruction": (
                "请按以下结构组织文章，面向建筑/设计专业人士：\n"
                "1. 开头：点明技术背景与解决的问题，呼应行业痛点\n"
                "2. 原理拆解：清晰讲解技术原理、系统组成与关键技术参数\n"
                "3. 规范与标准：说明符合的相关规范/标准要求\n"
                "4. 设计应用：给出设计中如何应用/选型的要点\n"
                "5. 结尾：总结技术价值与适用场景"
            ),
        },
        {
            "name": "方案对比型（设计师）",
            "type": "structure",
            "sort_order": 22,
            "prompt_instruction": (
                "请按以下结构组织文章，面向设计师/技术选型人员：\n"
                "1. 开头：说明对比的背景和维度\n"
                "2. 维度一：技术原理对比\n"
                "3. 维度二：性能与参数对比\n"
                "4. 维度三：成本与施工复杂度对比\n"
                "5. 结论：按场景给出选型建议（含适用/不适用条件）"
            ),
        },
        {
            "name": "专业权威（设计师）",
            "type": "style",
            "sort_order": 23,
            "prompt_instruction": (
                "语气风格要求（面向设计师/专业人士）：\n"
                "- 使用准确的专业术语（可含英文缩写）\n"
                "- 引用具体数据、参数、规范支撑观点\n"
                "- 客观、严谨、逻辑严密，避免夸大\n"
                "- 结构清晰，便于专业读者快速提取关键信息"
            ),
        },
    ],
    "dealer": [
        {
            "name": "招商政策解读型（经销商）",
            "type": "structure",
            "sort_order": 31,
            "prompt_instruction": (
                "请按以下结构组织文章，面向意向经销商/加盟商：\n"
                "1. 开头：点明当下合作/加盟机会与背景\n"
                "2. 政策解读：清晰解读合作模式、支持政策（培训/物料/区域保护等）\n"
                "3. 门槛与条件：说明合作条件与投入\n"
                "4. 收益分析：从经销商角度分析利润空间与回报\n"
                "5. 结尾：明确下一步行动（如何联系/申请），给出行动号召"
            ),
        },
        {
            "name": "市场机遇分析型（经销商）",
            "type": "structure",
            "sort_order": 32,
            "prompt_instruction": (
                "请按以下结构组织文章，面向经销商/渠道经营者：\n"
                "1. 开头：点出行业趋势与市场机会\n"
                "2. 市场分析：分析目标市场容量、增长趋势与需求\n"
                "3. 机会点：指出经销商可切入的机会与优势\n"
                "4. 竞争对比：说明选择本品牌/产品相对竞争对手的优势\n"
                "5. 结尾：呼吁把握机遇，引导进一步了解"
            ),
        },
        {
            "name": "营销转化（经销商）",
            "type": "style",
            "sort_order": 33,
            "prompt_instruction": (
                "语气风格要求（面向经销商/渠道经营者）：\n"
                "- 先制造痛点与机遇共鸣（为什么现在是好时机）\n"
                "- 突出合作的价值点与差异化优势\n"
                "- 用数据量化收益与支持\n"
                "- 结尾给出明确、低门槛的行动号召"
            ),
        },
    ],
}

_ALL_PRESETS: list[tuple[str | None, dict]] = [
    (None, t) for t in PRESET_TEMPLATES
] + [
    (at, t) for at, templates in ACCOUNT_PRESET_TEMPLATES.items() for t in templates
]


class TemplateService:
    """写作模板 CRUD 服务"""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def seed_presets(self) -> None:
        """增量写入预设模板（不覆盖已有记录，幂等）。"""
        added = 0
        for account_type, tmpl in _ALL_PRESETS:
            q = select(WritingTemplate).where(
                WritingTemplate.is_preset == 1,
                WritingTemplate.name == tmpl["name"],
                WritingTemplate.account_type == account_type,
            )
            exists = (await self.db.execute(q)).scalar_one_or_none()
            if exists:
                continue
            obj = WritingTemplate(
                user_id=0,
                name=tmpl["name"],
                type=tmpl["type"],
                account_type=account_type,
                prompt_instruction=tmpl["prompt_instruction"],
                is_preset=1,
                sort_order=tmpl["sort_order"],
            )
            self.db.add(obj)
            added += 1
        if added:
            await self.db.commit()
            logger.info("preset_templates_seeded", count=added)

    async def list_templates(self, user_id: int) -> list[WritingTemplate]:
        q = select(WritingTemplate).where(
            (WritingTemplate.is_preset == 1) | (WritingTemplate.user_id == user_id)
        ).order_by(WritingTemplate.sort_order, WritingTemplate.id)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def list_templates_by_account_type(
        self, account_type: str, user_id: int
    ) -> list[WritingTemplate]:
        """列出指定账号类型的模板：该类型预设 + 通用预设 + 用户自定义通用模板。"""
        q = select(WritingTemplate).where(
            WritingTemplate.is_preset == 1,
            (WritingTemplate.account_type == account_type)
            | (WritingTemplate.account_type.is_(None)),
        ).order_by(WritingTemplate.sort_order, WritingTemplate.id)
        if user_id:
            q = q.union(
                select(WritingTemplate).where(
                    WritingTemplate.user_id == user_id,
                    WritingTemplate.is_preset == 0,
                )
            ).order_by(WritingTemplate.sort_order, WritingTemplate.id)
        result = await self.db.execute(q)
        return list(result.scalars().all())

    async def resolve_account_template_ids(self, account_type: str) -> list[int]:
        """返回指定账号类型的预设模板 ID 列表（用于生成时自动注入指令）。"""
        q = select(WritingTemplate).where(
            WritingTemplate.is_preset == 1,
            WritingTemplate.account_type == account_type,
        ).order_by(WritingTemplate.sort_order, WritingTemplate.id)
        result = await self.db.execute(q)
        return [t.id for t in result.scalars().all()]

    async def create_template(
        self,
        user_id: int,
        name: str,
        type: str,
        prompt_instruction: str,
        account_type: str | None = None,
    ) -> WritingTemplate:
        obj = WritingTemplate(
            user_id=user_id,
            name=name,
            type=type,
            account_type=account_type,
            prompt_instruction=prompt_instruction,
            is_preset=0,
        )
        self.db.add(obj)
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def update_template(self, template_id: int, user_id: int, data: dict) -> WritingTemplate | None:
        q = select(WritingTemplate).where(
            WritingTemplate.id == template_id,
        )
        obj = (await self.db.execute(q)).scalar_one_or_none()
        if not obj:
            return None
        if data.get("name") is not None:
            obj.name = data["name"]
        if data.get("prompt_instruction") is not None:
            obj.prompt_instruction = data["prompt_instruction"]
        await self.db.commit()
        await self.db.refresh(obj)
        return obj

    async def delete_template(self, template_id: int, user_id: int) -> bool:
        q = select(WritingTemplate).where(
            WritingTemplate.id == template_id,
        )
        obj = (await self.db.execute(q)).scalar_one_or_none()
        if not obj:
            return False
        await self.db.delete(obj)
        await self.db.commit()
        return True


async def get_template_instructions(template_ids: list[int], db: AsyncSession) -> str:
    """根据模板 ID 列表拼接 LLM 指令文本"""
    if not template_ids:
        return ""

    q = select(WritingTemplate).where(WritingTemplate.id.in_(template_ids))
    result = await db.execute(q)
    templates = list(result.scalars().all())

    if not templates:
        return ""

    parts = ["## 写作模板要求（必须严格遵循）"]
    for t in templates:
        parts.append(f"\n### {t.name}\n{t.prompt_instruction}")

    return "\n".join(parts)
