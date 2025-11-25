"""
Prompt 관리 모듈

프롬프트 파일을 로드하고 관리하는 유틸리티
"""
from pathlib import Path
from typing import Dict


class PromptLoader:
    """프롬프트 파일 로더"""

    def __init__(self):
        self.prompts_dir = Path(__file__).parent
        self._cache: Dict[str, str] = {}

    def load(self, prompt_name: str) -> str:
        """
        프롬프트 파일 로드 (캐싱)

        Args:
            prompt_name: 프롬프트 이름 (확장자 제외)
                        예: "qa_prompt", "temporal_intent_prompt"

        Returns:
            str: 프롬프트 템플릿 문자열

        Raises:
            FileNotFoundError: 프롬프트 파일이 없는 경우
        """
        # 캐시 확인
        if prompt_name in self._cache:
            return self._cache[prompt_name]

        # 파일 경로
        prompt_path = self.prompts_dir / f"{prompt_name}.txt"

        # 파일 존재 확인
        if not prompt_path.exists():
            raise FileNotFoundError(
                f"프롬프트 파일을 찾을 수 없습니다: {prompt_path}"
            )

        # 파일 읽기
        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_template = f.read()

        # 캐시 저장
        self._cache[prompt_name] = prompt_template

        return prompt_template

    def get_qa_prompt(self) -> str:
        """QA 프롬프트 로드"""
        return self.load("qa_prompt")

    def get_temporal_intent_prompt(self) -> str:
        """시간 의도 파싱 프롬프트 로드"""
        return self.load("temporal_intent_prompt")


# 싱글톤 인스턴스
_prompt_loader = None


def get_prompt_loader() -> PromptLoader:
    """
    PromptLoader 싱글톤 인스턴스 반환

    Returns:
        PromptLoader: 프롬프트 로더 인스턴스
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader()
    return _prompt_loader


# 편의 함수
def load_prompt(prompt_name: str) -> str:
    """프롬프트 로드 (편의 함수)"""
    return get_prompt_loader().load(prompt_name)


def get_qa_prompt() -> str:
    """QA 프롬프트 로드 (편의 함수)"""
    return get_prompt_loader().get_qa_prompt()


def get_temporal_intent_prompt() -> str:
    """시간 의도 파싱 프롬프트 로드 (편의 함수)"""
    return get_prompt_loader().get_temporal_intent_prompt()
