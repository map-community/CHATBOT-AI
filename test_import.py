"""
간단한 import 테스트 스크립트
어디서 에러가 나는지 확인
"""
print("=" * 50)
print("🔍 Import 테스트 시작")
print("=" * 50)

try:
    print("1️⃣ dotenv 로딩 테스트...")
    from dotenv import load_dotenv
    import os
    load_dotenv()
    print("   ✅ dotenv 로딩 성공")

    print("\n2️⃣ 환경변수 확인...")
    pinecone_key = os.getenv('PINECONE_API_KEY')
    upstage_key = os.getenv('UPSTAGE_API_KEY')
    print(f"   PINECONE_API_KEY: {'✅ 설정됨' if pinecone_key else '❌ 없음'}")
    print(f"   UPSTAGE_API_KEY: {'✅ 설정됨' if upstage_key else '❌ 없음'}")

    if pinecone_key:
        print(f"   Pinecone Key 앞 10자: {pinecone_key[:10]}...")
    if upstage_key:
        print(f"   Upstage Key 앞 10자: {upstage_key[:10]}...")

    print("\n3️⃣ 기본 패키지 import 테스트...")
    import flask
    print("   ✅ Flask")
    import redis
    print("   ✅ Redis")
    import pymongo
    print("   ✅ PyMongo")

    print("\n4️⃣ AI 패키지 import 테스트...")
    import pinecone
    print("   ✅ Pinecone")
    from langchain_upstage import UpstageEmbeddings, ChatUpstage
    print("   ✅ LangChain Upstage")

    print("\n5️⃣ NLP 패키지 import 테스트...")
    import nltk
    print("   ✅ NLTK")
    from konlpy.tag import Okt
    print("   ✅ KoNLPy")

    print("\n6️⃣ ai_modules.py import 테스트...")
    print("   (이 단계가 오래 걸릴 수 있습니다...)")
    import sys
    sys.path.insert(0, 'src')
    from modules import ai_modules
    print("   ✅ ai_modules 로딩 성공!")

    print("\n" + "=" * 50)
    print("🎉 모든 테스트 통과!")
    print("=" * 50)

except ImportError as e:
    print(f"\n❌ Import 에러 발생: {e}")
    print(f"   에러 타입: {type(e).__name__}")
    import traceback
    print("\n상세 에러:")
    traceback.print_exc()

except Exception as e:
    print(f"\n❌ 예상치 못한 에러 발생: {e}")
    print(f"   에러 타입: {type(e).__name__}")
    import traceback
    print("\n상세 에러:")
    traceback.print_exc()
