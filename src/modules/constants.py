"""
전역 상수 정의

매직 스트링과 공통 상수를 중앙에서 관리
"""

# 콘텐츠 부재를 나타내는 상수
EMPTY_CONTENT = ""  # 빈 콘텐츠 (이전 "No content" 대체)

# 날짜 관련 상수
UNKNOWN_DATE = ""  # 날짜 정보 없음 (이전 "Unknown Date" 대체)

# 제목 관련 상수
UNKNOWN_TITLE = "Unknown Title"  # 제목 정보 없음

# 콘텐츠 타입 (Pinecone 메타데이터용)
CONTENT_TYPE_TEXT = "text"
CONTENT_TYPE_IMAGE = "image"
CONTENT_TYPE_ATTACHMENT = "attachment"

# 콘텐츠 소스 (Pinecone 메타데이터용)
SOURCE_ORIGINAL_POST = "original_post"
SOURCE_IMAGE_OCR = "image_ocr"
SOURCE_DOCUMENT_PARSE = "document_parse"

# 카테고리 (Pinecone 메타데이터용)
CATEGORY_NOTICE = "notice"
CATEGORY_JOB = "job"
CATEGORY_SEMINAR = "seminar"
CATEGORY_PROFESSOR = "professor"
