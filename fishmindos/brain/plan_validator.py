"""
规划验证和自适应改进模块。
检测常见错误，从失败中学习，自动改进规划质量。
"""

from typing import List, Dict, Any, Tuple, Optional
import re


class PlanValidator:
    """
    验证和改进任务规划的工具类。
    检测：
    - 缺失的灯光/播报请求
    - 颠倒的步骤顺序
    - 导航后缺少等待
    - 其他逻辑错误
    """

    def __init__(self):
        self.common_errors = []

    def validate_plan(self, user_input: str, steps: List[Dict[str, Any]]) -> Tuple[bool, List[str]]:
        """
        验证规划是否满足用户需求。
        
        返回: (是否有效, 问题列表)
        """
        issues = []

        # 1. 检查是否漏掉了灯光请求
        light_keywords = ["闪", "亮", "暗", "灯", "亮绿灯", "亮红灯", "关灯"]
        has_light_request = any(kw in user_input for kw in light_keywords)
        has_light_action = any(s.get("skill") in ["light_set", "light_on", "light_off"] for s in steps)

        if has_light_request and not has_light_action:
            issues.append("用户要求灯光操作，但规划中没有灯光技能")

        # 2. 检查是否漏掉了播报请求
        audio_keywords = ["播报", "说", "讲", "告诉"]
        has_audio_request = any(kw in user_input for kw in audio_keywords)
        has_audio_action = any(s.get("skill") in ["audio_say", "audio_play"] for s in steps)

        if has_audio_request and not has_audio_action:
            issues.append("用户要求播报/语音，但规划中没有音频技能")

        # 3. 检查导航序列的完整性
        nav_issues = self._check_navigation_sequence(steps)
        issues.extend(nav_issues)

        # 4. 检查步骤顺序逻辑
        order_issues = self._check_step_order(steps, user_input)
        issues.extend(order_issues)

        return len(issues) == 0, issues

    def _check_navigation_sequence(self, steps: List[Dict[str, Any]]) -> List[str]:
        """检查导航步骤是否完整（导航后需要等待）。"""
        issues = []
        nav_indexes = []
        wait_indexes = []

        for i, step in enumerate(steps):
            if step.get("skill") == "nav_goto_location":
                nav_indexes.append(i)
            elif step.get("skill") == "system_wait":
                wait_indexes.append(i)

        # 检查每个导航后是否有对应的等待
        for nav_idx in nav_indexes:
            has_following_wait = any(
                wait_idx > nav_idx and wait_idx == nav_idx + 1
                for wait_idx in wait_indexes
            )
            if not has_following_wait:
                # 检查是否有某个 wait 跟在这个 nav 后面（可能不相邻）
                has_any_wait_after = any(wait_idx > nav_idx for wait_idx in wait_indexes)
                if has_any_wait_after:
                    issues.append(f"导航步骤（位置{nav_idx}）后可能缺少等待，或步骤顺序不对")

        return issues

    def _check_step_order(self, steps: List[Dict[str, Any]], user_input: str) -> List[str]:
        """检查步骤顺序是否合理。"""
        issues = []

        # 获取步骤类型序列
        step_types = [s.get("skill") for s in steps]

        # 灯光/播报不应该在导航前
        light_audio_skills = {"light_set", "light_on", "light_off", "audio_say", "audio_play"}
        nav_skills = {"nav_goto_location"}

        for i, skill in enumerate(step_types):
            if skill in light_audio_skills:
                # 检查前面是否有导航
                has_nav_before = any(
                    step_types[j] in nav_skills for j in range(i)
                )
                # 检查后面是否有导航
                has_nav_after = any(
                    step_types[j] in nav_skills for j in range(i + 1, len(step_types))
                )

                # 如果前面有导航，往往意味着应该在对应的等待后加灯光
                if has_nav_before and has_nav_after:
                    # 这可能表示顺序错了
                    issues.append(
                        f"灯光/播报步骤位置可能不对（位置{i}）：通常应该在到达某个目标后执行，"
                        f"而不是在多个导航之间"
                    )

        return issues

    def get_improvement_hint(self, issues: List[str]) -> str:
        """
        根据检测到的问题，生成改进提示给 LLM。
        """
        if not issues:
            return ""

        lines = ["### 规划审查反馈"]
        lines.append("检测到以下问题，请改进规划：")
        for i, issue in enumerate(issues, 1):
            lines.append(f"{i}. {issue}")

        lines.append("")
        lines.append("**改进建议**:")
        for i, issue in enumerate(issues, 1):
            if "灯光" in issue:
                lines.append(
                    f"  - 问题{i}：在导航完成（system_wait）后添加灯光技能"
                )
            elif "播报" in issue:
                lines.append(
                    f"  - 问题{i}：在合适的位置添加 audio_say 技能"
                )
            elif "等待" in issue:
                lines.append(
                    f"  - 问题{i}：在 nav_goto_location 后立即添加 system_wait(event_type=arrival 或 dock_complete)"
                )
            elif "顺序" in issue:
                lines.append(
                    f"  - 问题{i}：调整步骤顺序，确保灯光/播报在合理的位置"
                )

        return "\n".join(lines)

    def extract_user_intent(self, user_input: str) -> Dict[str, Any]:
        """
        从用户输入中提取意图，帮助检查规划是否完整。
        """
        intent = {
            "has_navigation": False,
            "nav_targets": [],
            "has_light": False,
            "light_type": None,
            "has_audio": False,
            "audio_content": None,
            "return_to_charge": False,
        }

        # 检查导航意图
        nav_keywords = ["去", "前往", "导航", "到", "回"]
        if any(kw in user_input for kw in nav_keywords):
            intent["has_navigation"] = True

            # 提取目标位置
            locations = ["厕所", "卫生间", "会议室", "大厅", "充电", "回充点"]
            for loc in locations:
                if loc in user_input:
                    intent["nav_targets"].append(loc)

            if "回" in user_input and "充" in user_input:
                intent["return_to_charge"] = True

        # 检查灯光意图
        light_keywords = ["闪", "亮", "暗", "灯"]
        if any(kw in user_input for kw in light_keywords):
            intent["has_light"] = True
            if "绿" in user_input:
                intent["light_type"] = "green"
            elif "红" in user_input:
                intent["light_type"] = "red"
            elif "黄" in user_input:
                intent["light_type"] = "yellow"

            if "闪" in user_input:
                intent["light_mode"] = "slow"  # 默认慢闪

        # 检查音频意图
        audio_keywords = ["播报", "说", "讲"]
        if any(kw in user_input for kw in audio_keywords):
            intent["has_audio"] = True

        return intent
