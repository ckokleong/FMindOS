"""
音频控制技能
"""

from typing import Any, Dict
from fishmindos.core.models import SkillContext, SkillResult
from fishmindos.skills.base import Skill


class PlayAudioSkill(Skill):
    """播放语音技能"""
    name = "audio_play"
    description = "让机器狗播放语音"
    category = "audio"
    
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要播放的文本内容"
            }
        },
        "required": ["text"]
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        text = params.get("text")
        
        if not text:
            return SkillResult(False, "请提供要播放的文本")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        success = self.adapter.play_audio(text)
        if success:
            return SkillResult(True, f"正在播报: {text}")
        return SkillResult(False, "语音播报失败")


class TTSSkill(Skill):
    """TTS文字转语音技能"""
    name = "tts_speak"
    description = "使用TTS播报文本"
    category = "audio"
    
    parameters = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要播报的文本"
            },
            "wait": {
                "type": "boolean",
                "description": "是否等待播报完成",
                "default": True
            }
        },
        "required": ["text"]
    }
    
    def execute(self, params: Dict[str, Any], context: SkillContext) -> SkillResult:
        text = params.get("text")
        
        if not text:
            return SkillResult(False, "请提供要播报的文本")
        
        if not self.adapter:
            return SkillResult(False, "适配器未设置")
        
        success = self.adapter.play_audio(text)
        if success:
            return SkillResult(True, f"播报: {text}")
        return SkillResult(False, "播报失败")
