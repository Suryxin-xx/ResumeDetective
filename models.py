"""
数据模型定义（dataclass）
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Resume:
    """简历模型"""
    id: Optional[int] = None
    company_name: str = ""
    position_name: str = ""
    file_path: str = ""
    jd_text: str = ""
    application_source: str = ""
    job_link: str = ""
    upload_time: str = ""
    version_note: str = ""


@dataclass
class Application:
    """投递记录模型"""
    id: Optional[int] = None
    resume_id: int = 0
    current_status: str = "已投递"
    status_update_time: str = ""
    interview_feedback: str = ""
    next_action: str = ""
    # 联表时附带的简历信息
    company_name: str = ""
    position_name: str = ""
    file_path: str = ""
    jd_text: str = ""


@dataclass
class Material:
    """个人经历碎片模型"""
    id: Optional[int] = None
    material_type: str = ""
    title: str = ""
    content: str = ""
    tags: str = ""
    start_time: str = ""
    end_time: str = ""
    created_at: str = ""


@dataclass
class Profile:
    """个人信息模型"""
    id: Optional[int] = None
    full_name: str = ""
    gender: str = ""
    birth_date: str = ""
    phone: str = ""
    email: str = ""
    city: str = ""
    education: str = ""
    school: str = ""
    major: str = ""
    target_role: str = ""
    summary: str = ""
    github_url: str = ""
    portfolio_url: str = ""
    updated_at: str = ""


@dataclass
class JobTarget:
    """意向公司/岗位模型"""
    id: Optional[int] = None
    company_name: str = ""
    position_name: str = ""
    jd_text: str = ""
    jd_link: str = ""
    city: str = ""
    status: str = "待研究"  # 待研究 / 待投递 / 已投递 / 暂不考虑
    notes: str = ""
    created_at: str = ""
    updated_at: str = ""
