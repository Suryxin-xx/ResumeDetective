"""
AI 服务模块
DeepSeek 流式 API 调用 + 脱敏 + Prompt 组装
"""

import re
import json

import requests


def desensitize(text):
    """脱敏：替换手机号和邮箱"""
    text = re.sub(r'1[3-9]\d{9}', '[手机号隐去]', text)
    text = re.sub(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}', '[邮箱隐去]', text)
    return text


def build_prompt(company, position, status, jd_text, materials, user_question):
    """组装 System Prompt + User Prompt"""
    system = (
        f"你是一位资深互联网大厂面试官。"
        f"用户正在申请【{company}】的【{position}】岗位，"
        f"当前阶段为【{status}】。"
        f"请严格基于用户提供的'个人经历碎片'进行回答。"
        f"严禁编造用户未提供的经历。"
    )
    parts = []
    if jd_text:
        parts.append(f"【岗位描述】\n{jd_text}\n")
    if materials:
        parts.append("【个人经历碎片】")
        for m in materials:
            parts.append(f"- [{m.get('material_type','经历')}] "
                         f"{m.get('title','')}: {m.get('content','')}")
        parts.append("")
    parts.append(f"【我的问题】\n{user_question}")
    user = desensitize("\n".join(parts))
    return system, user


def build_resume_draft_prompt(jd, profile, materials):
    """生成简历初稿的 Prompt"""
    system = (
        "你是一位专业的简历优化顾问。你的任务是帮助用户生成一份针对特定岗位的简历初稿。\n"
        "规则：\n"
        "1. 严格基于用户提供的个人信息和经历碎片，不要编造任何未提供的经历。\n"
        "2. 针对目标 JD 的要求，从用户的经历中筛选最相关的条目进行优化描述。\n"
        "3. 使用 STAR 法则（情境-任务-行动-结果）改写项目经历，突出量化成果。\n"
        "4. 输出格式为 Markdown，结构清晰。\n"
        "5. 如果没有足够的相关经历匹配 JD，诚实说明差距并给出建议。"
    )
    parts = ["请根据以下信息生成一份简历初稿（Markdown 格式）：\n"]
    if jd:
        parts.append(f"## 目标岗位描述\n{jd}\n")
    if profile:
        p = profile
        parts.append("## 个人信息")
        parts.append(f"- 姓名：{p.get('full_name','')}")
        parts.append(f"- 电话：{p.get('phone','')}")
        parts.append(f"- 邮箱：{p.get('email','')}")
        parts.append(f"- 城市：{p.get('city','')}")
        parts.append(f"- 学校：{p.get('school','')} | {p.get('major','')} | {p.get('education','')}")
        parts.append(f"- 求职方向：{p.get('target_role','')}")
        if p.get('summary'):
            parts.append(f"\n个人总结：{p['summary']}\n")
        parts.append("")
    if materials:
        parts.append("## 经历碎片")
        for m in materials:
            parts.append(f"- [{m.get('material_type','经历')}] {m.get('title','')}")
            time_str = ""
            if m.get('start_time'):
                time_str = f" ({m['start_time']} ~ {m.get('end_time','至今')})"
            parts.append(f"  描述：{m['content']}{time_str}")
        parts.append("")
    parts.append("请输出完整简历初稿，包含：个人简介、教育背景、相关经历（按 JD 匹配度排序）、技能标签。")
    return system, desensitize("\n".join(parts))


def build_jd_analysis_prompt(jd):
    """JD 关键词提取与能力要求总结"""
    system = (
        "你是一位资深的求职策略分析师。请对以下岗位描述进行深度分析，"
        "提取关键信息并以结构化 Markdown 输出。"
    )
    prompt = (
        f"请对以下 JD 进行深度分析，输出格式如下：\n\n"
        f"## 1. 核心职责概述\n"
        f"（用 2-3 句话概括这个岗位主要做什么）\n\n"
        f"## 2. 硬性要求\n"
        f"- 学历/专业要求\n"
        f"- 技能要求（编程语言、工具、框架等）\n"
        f"- 经验要求\n\n"
        f"## 3. 软性要求\n"
        f"- 沟通/协作\n"
        f"- 问题解决\n"
        f"- 其他软实力\n\n"
        f"## 4. 加分项\n"
        f"（列出让候选人脱颖而出的额外条件）\n\n"
        f"## 5. 能力匹配建议\n"
        f"（应聘者应重点展示哪些能力和经历）\n\n"
        f"### JD 原文：\n{jd}"
    )
    return system, prompt


def build_match_analysis_prompt(jd, profile, materials):
    """分析 JD 与个人资料的匹配度，并给出补强建议。"""
    system = (
        "你是一位资深求职顾问。请根据用户的目标 JD、个人信息和经历碎片，"
        "输出一份务实的岗位匹配分析。严禁编造用户未提供的经历。"
    )
    parts = ["请基于以下信息输出岗位匹配分析（Markdown）：\n"]
    parts.append(f"## 目标 JD\n{jd}\n")
    if profile:
        parts.append("## 个人信息")
        parts.append(f"- 学校/专业：{profile.get('school','')} / {profile.get('major','')}")
        parts.append(f"- 学历：{profile.get('education','')}")
        parts.append(f"- 目标方向：{profile.get('target_role','')}")
        if profile.get("summary"):
            parts.append(f"- 个人总结：{profile.get('summary','')}")
        parts.append("")
    if materials:
        parts.append("## 经历碎片")
        for m in materials[:8]:
            parts.append(
                f"- [{m.get('material_type','经历')}] {m.get('title','')}: {m.get('content','')}"
            )
        parts.append("")
    parts.append(
        "输出要求：\n"
        "1. 先给出整体匹配度结论（高/中/低）和理由\n"
        "2. 列出最匹配的 3 条经历\n"
        "3. 列出明显短板或缺口\n"
        "4. 给出简历改写重点\n"
        "5. 给出面试准备建议和下一步行动清单"
    )
    return system, desensitize("\n".join(parts))


def build_project_rewrite_prompt(material, jd=""):
    """针对岗位重写项目经历描述"""
    system = (
        "你是一位简历优化专家。请将以下一段经历碎片重写为更适合放入简历的格式，"
        "使用 STAR 法则，突出量化成果和对目标岗位的匹配度。"
    )
    prompt = f"请重写以下项目经历，使其更适合求职场景：\n"
    if jd:
        prompt += f"\n目标岗位要求：\n{jd}\n"
    prompt += (
        f"\n原始经历：\n"
        f"标题：{material.get('title','')}\n"
        f"类型：{material.get('material_type','')}\n"
        f"描述：{material.get('content','')}\n"
        f"\n输出要求：\n"
        f"1. 使用 STAR 法则改写\n"
        f"2. 突出量化成果（数据、效果）\n"
        f"3. 控制在 100-200 字以内\n"
        f"4. 与目标岗位要求对齐"
    )
    return system, prompt


def build_self_intro_prompt(profile, materials, jd=""):
    """生成自我介绍稿"""
    system = (
        "你是一位面试辅导专家。根据用户提供的个人信息和经历，"
        "生成一份适合求职面试的自我介绍稿。"
    )
    parts = ["请为我生成一份面试自我介绍稿：\n"]
    if jd:
        parts.append(f"目标岗位：\n{jd}\n")
    if profile:
        p = profile
        parts.append("## 个人背景")
        parts.append(f"- 姓名：{p.get('full_name','')}")
        parts.append(f"- 学校/专业：{p.get('school','')} {p.get('major','')}")
        parts.append(f"- 学历：{p.get('education','')}")
        if p.get('summary'):
            parts.append(f"- 个人总结：{p['summary']}")
        parts.append("")
    if materials:
        parts.append("## 主要经历")
        for m in materials[:5]:  # 取前 5 条
            parts.append(f"- {m.get('title','')}: {m.get('content','')[:100]}")
        parts.append("")
    parts.append("输出要求：\n"
                 "1. 时长控制在 1-2 分钟（约 300-400 字）\n"
                 "2. 结构：开场问候 → 教育背景 → 核心经历/项目 → 为什么适合该岗位 → 结束\n"
                 "3. 突出与目标岗位最相关的经历\n"
                 "4. 口语化，适合面试朗读")
    return system, desensitize("\n".join(parts))


def call_deepseek(api_key, messages, model=None):
    """调用 DeepSeek API（流式），返回生成器逐 token yield"""
    if not model:
        raise RuntimeError("未选择模型，请先通过 API 获取模型列表。")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": messages,
               "stream": True, "temperature": 0.7}
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions",
                             headers=headers, json=payload, stream=True, timeout=(10, 120))
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line:
                continue
            s = line.decode("utf-8").strip()
            if not s.startswith("data: "):
                continue
            d = s[6:]
            if d == "[DONE]":
                break
            try:
                c = json.loads(d)["choices"][0]["delta"].get("content", "")
                if c:
                    yield c
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
    except requests.exceptions.RequestException as e:
        raise RuntimeError(f"API 调用失败：{e}")
