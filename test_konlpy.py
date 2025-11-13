"""
KoNLPy 상세 테스트
"""
import sys
import os

print("=" * 60)
print("🔍 KoNLPy 상세 진단")
print("=" * 60)

print("\n1️⃣ Java 환경 확인...")
print(f"   JAVA_HOME: {os.environ.get('JAVA_HOME', '❌ 설정 안됨')}")

print("\n2️⃣ JPype1 import 테스트...")
try:
    import jpype
    print(f"   ✅ JPype1 버전: {jpype.__version__}")
except Exception as e:
    print(f"   ❌ JPype1 에러: {e}")
    sys.exit(1)

print("\n3️⃣ JPype1 JVM 시작 테스트...")
try:
    if not jpype.isJVMStarted():
        print("   🔄 JVM 시작 시도 중...")
        jpype.startJVM(jpype.getDefaultJVMPath(), "-ea")
        print("   ✅ JVM 시작 성공!")
    else:
        print("   ✅ JVM 이미 실행 중")
except Exception as e:
    print(f"   ❌ JVM 시작 실패: {e}")
    print(f"   JVM 경로: {jpype.getDefaultJVMPath()}")
    sys.exit(1)

print("\n4️⃣ KoNLPy 패키지 import 테스트...")
try:
    import konlpy
    print(f"   ✅ konlpy 버전: {konlpy.__version__}")
except Exception as e:
    print(f"   ❌ konlpy import 에러: {e}")
    sys.exit(1)

print("\n5️⃣ Okt 클래스 import 테스트...")
try:
    from konlpy.tag import Okt
    print("   ✅ Okt import 성공!")
except Exception as e:
    print(f"   ❌ Okt import 에러: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n6️⃣ Okt 인스턴스 생성 테스트...")
try:
    okt = Okt()
    print("   ✅ Okt 인스턴스 생성 성공!")
except Exception as e:
    print(f"   ❌ Okt 인스턴스 생성 실패: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n7️⃣ 간단한 형태소 분석 테스트...")
try:
    result = okt.morphs("안녕하세요")
    print(f"   ✅ 형태소 분석 결과: {result}")
except Exception as e:
    print(f"   ❌ 형태소 분석 실패: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("🎉 KoNLPy 모든 테스트 통과!")
print("=" * 60)
