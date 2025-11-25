"""
ML/AI 설정 관리 모듈

ml_config.yaml 파일을 로드하고 타입 안전하게 접근할 수 있는 인터페이스 제공
"""
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class TextProcessingConfig:
    """텍스트 처리 설정"""
    chunk_size: int = 850
    chunk_overlap: int = 100


@dataclass
class BM25Config:
    """BM25 검색 알고리즘 설정"""
    k1: float = 1.5
    b: float = 0.75


@dataclass
class DenseRetrievalConfig:
    """Dense Retrieval 설정"""
    similarity_scale: float = 3.26
    noun_weight: float = 0.20
    digit_weight: float = 0.24


@dataclass
class ClusteringConfig:
    """문서 클러스터링 설정"""
    similarity_threshold: float = 0.89


@dataclass
class ZipProcessingConfig:
    """ZIP 파일 처리 설정"""
    max_zip_size: int = 104857600  # 100MB
    max_total_files: int = 50
    max_extraction_size: int = 524288000  # 500MB


@dataclass
class MLConfig:
    """ML/AI 전체 설정"""
    text_processing: TextProcessingConfig
    bm25: BM25Config
    dense_retrieval: DenseRetrievalConfig
    clustering: ClusteringConfig
    zip_processing: ZipProcessingConfig

    @classmethod
    def from_yaml(cls, yaml_path: Optional[str] = None) -> 'MLConfig':
        """
        YAML 파일에서 설정 로드

        Args:
            yaml_path: YAML 파일 경로 (기본값: config/ml_config.yaml)

        Returns:
            MLConfig: 설정 객체

        Raises:
            FileNotFoundError: YAML 파일이 없는 경우
            ValueError: YAML 파싱 오류
        """
        # 기본 경로
        if yaml_path is None:
            config_dir = Path(__file__).parent
            yaml_path = config_dir / "ml_config.yaml"
        else:
            yaml_path = Path(yaml_path)

        # 파일 존재 확인
        if not yaml_path.exists():
            raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {yaml_path}")

        # YAML 로드
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config_dict = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"YAML 파싱 오류: {e}")

        # 설정 객체 생성
        return cls(
            text_processing=TextProcessingConfig(
                **config_dict.get('text_processing', {})
            ),
            bm25=BM25Config(
                **config_dict.get('bm25', {})
            ),
            dense_retrieval=DenseRetrievalConfig(
                **config_dict.get('dense_retrieval', {})
            ),
            clustering=ClusteringConfig(
                **config_dict.get('clustering', {})
            ),
            zip_processing=ZipProcessingConfig(
                **config_dict.get('zip_processing', {})
            )
        )

    @classmethod
    def default(cls) -> 'MLConfig':
        """
        기본 설정 반환 (YAML 없이 사용 가능)

        Returns:
            MLConfig: 기본값으로 초기화된 설정 객체
        """
        return cls(
            text_processing=TextProcessingConfig(),
            bm25=BM25Config(),
            dense_retrieval=DenseRetrievalConfig(),
            clustering=ClusteringConfig(),
            zip_processing=ZipProcessingConfig()
        )


# ============================================================
# 싱글톤 패턴으로 전역 설정 관리
# ============================================================
_ml_config: Optional[MLConfig] = None


def get_ml_config(reload: bool = False) -> MLConfig:
    """
    ML 설정 싱글톤 인스턴스 반환

    Args:
        reload: 설정을 다시 로드할지 여부 (기본값: False)

    Returns:
        MLConfig: ML 설정 객체
    """
    global _ml_config

    if _ml_config is None or reload:
        try:
            _ml_config = MLConfig.from_yaml()
        except FileNotFoundError:
            # YAML 파일이 없으면 기본값 사용
            _ml_config = MLConfig.default()

    return _ml_config


def reload_ml_config():
    """
    설정을 다시 로드 (테스트나 실험 시 유용)
    """
    return get_ml_config(reload=True)


# ============================================================
# 편의 함수 (Backward Compatibility)
# ============================================================
# 기존 코드와의 호환성을 위한 상수들
# 추후 제거 예정
def get_chunk_size() -> int:
    """청크 크기 반환"""
    return get_ml_config().text_processing.chunk_size


def get_chunk_overlap() -> int:
    """청크 겹침 반환"""
    return get_ml_config().text_processing.chunk_overlap


def get_bm25_k1() -> float:
    """BM25 k1 파라미터 반환"""
    return get_ml_config().bm25.k1


def get_bm25_b() -> float:
    """BM25 b 파라미터 반환"""
    return get_ml_config().bm25.b
