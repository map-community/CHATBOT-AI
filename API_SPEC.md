# KNU 챗봇 API 명세서

Flutter 앱 또는 다른 클라이언트에서 KNU 컴퓨터학부 AI 챗봇 API를 사용하기 위한 명세서입니다.

## 📋 기본 정보

### Base URL

```
http://localhost:5000
```

**프로덕션 환경**: 실제 배포 시 도메인으로 변경 필요

### Content-Type

모든 요청/응답은 `application/json` 형식을 사용합니다.

### CORS

CORS가 활성화되어 있어 모든 도메인에서 접근 가능합니다.

---

## 🔌 엔드포인트

### 1. Health Check

서버 상태를 확인합니다.

#### 요청

```http
GET /health
```

**Parameters**: None

#### 응답

**Success (200 OK)**

```json
{
  "status": "healthy",
  "message": "KNU Chatbot Server is running",
  "version": "1.0.0"
}
```

**Response Fields**:
- `status` (string): 서버 상태 (`"healthy"`)
- `message` (string): 상태 메시지
- `version` (string): API 버전

#### Flutter 예시

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

Future<Map<String, dynamic>> checkHealth() async {
  final response = await http.get(
    Uri.parse('http://localhost:5000/health'),
  );

  if (response.statusCode == 200) {
    return json.decode(response.body);
  } else {
    throw Exception('Failed to check health');
  }
}
```

---

### 2. AI 챗봇 응답

사용자 질문에 대한 AI 답변을 받습니다.

#### 요청

```http
POST /ai/ai-response
Content-Type: application/json
```

**Request Body**:

```json
{
  "question": "컴퓨터학부 졸업요건이 뭐야?"
}
```

**Request Fields**:
- `question` (string, required): 사용자 질문
  - 최소 1자 이상
  - 공백만 있는 문자열 불가
  - UTF-8 인코딩 (한글 지원)

#### 응답

**Success (200 OK)**

```json
{
  "answer": "컴퓨터학부 졸업요건은 학칙 및 경북대학교 교육과정 운영 및 이수에 관한 지침에 의거하여 다음과 같습니다.\n\n1. 총 이수학점: 130학점\n2. 글솝 교육과정 내 컴퓨터학부 개설 전공: 51학점\n3. 교양 및 기타(다중, 해외, 석사, 현장실습 등): 총 이수학점이 130학점이 되도록 이수",
  "references": "\n참고 문서 URL: https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=25900",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": ["No content"]
}
```

**Response Fields**:
- `answer` (string | null): AI가 생성한 답변
  - `null`인 경우: 이미지로만 답변 제공
  - 줄바꿈 문자(`\n`) 포함 가능
- `references` (string): 참고 문서 URL
  - 공지사항 URL 또는 안내 URL
- `disclaimer` (string): 면책 조항
- `images` (array of strings): 관련 이미지 URL 목록
  - `["No content"]`: 이미지 없음
  - 이미지가 있는 경우 URL 배열

#### 에러 응답

**Bad Request (400)**

```json
{
  "error": "No JSON data provided"
}
```

또는

```json
{
  "error": "Invalid or missing question"
}
```

**Internal Server Error (500)**

```json
{
  "error": "division by zero"
}
```

또는

```json
{
  "error": "Invalid response format from AI module"
}
```

#### Flutter 예시

**1. 기본 HTTP 요청 (http 패키지)**

```dart
import 'package:http/http.dart' as http;
import 'dart:convert';

class ChatbotService {
  static const String baseUrl = 'http://localhost:5000';

  Future<Map<String, dynamic>> sendQuestion(String question) async {
    final response = await http.post(
      Uri.parse('$baseUrl/ai/ai-response'),
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
      },
      body: json.encode({
        'question': question,
      }),
    );

    if (response.statusCode == 200) {
      return json.decode(utf8.decode(response.bodyBytes));
    } else {
      final error = json.decode(response.body);
      throw Exception(error['error'] ?? 'Unknown error');
    }
  }
}

// 사용 예시
void main() async {
  final service = ChatbotService();

  try {
    final result = await service.sendQuestion('컴퓨터학부 졸업요건이 뭐야?');
    print('답변: ${result['answer']}');
    print('참고: ${result['references']}');
  } catch (e) {
    print('에러 발생: $e');
  }
}
```

**2. Dio 패키지 사용**

```dart
import 'package:dio/dio.dart';

class ChatbotService {
  final Dio _dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:5000',
    contentType: 'application/json; charset=utf-8',
    connectTimeout: Duration(seconds: 30),
    receiveTimeout: Duration(seconds: 30),
  ));

  Future<ChatbotResponse> sendQuestion(String question) async {
    try {
      final response = await _dio.post(
        '/ai/ai-response',
        data: {'question': question},
      );

      return ChatbotResponse.fromJson(response.data);
    } on DioException catch (e) {
      if (e.response != null) {
        throw Exception(e.response!.data['error'] ?? 'Unknown error');
      } else {
        throw Exception('Network error: ${e.message}');
      }
    }
  }
}

// 모델 클래스
class ChatbotResponse {
  final String? answer;
  final String references;
  final String disclaimer;
  final List<String> images;

  ChatbotResponse({
    this.answer,
    required this.references,
    required this.disclaimer,
    required this.images,
  });

  factory ChatbotResponse.fromJson(Map<String, dynamic> json) {
    return ChatbotResponse(
      answer: json['answer'],
      references: json['references'],
      disclaimer: json['disclaimer'],
      images: List<String>.from(json['images']),
    );
  }

  bool get hasImages => images.isNotEmpty && images.first != 'No content';
}
```

**3. Provider와 함께 사용**

```dart
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

class ChatbotProvider extends ChangeNotifier {
  final ChatbotService _service = ChatbotService();

  bool _isLoading = false;
  ChatbotResponse? _lastResponse;
  String? _error;

  bool get isLoading => _isLoading;
  ChatbotResponse? get lastResponse => _lastResponse;
  String? get error => _error;

  Future<void> askQuestion(String question) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      _lastResponse = await _service.sendQuestion(question);
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}

// UI에서 사용
class ChatScreen extends StatelessWidget {
  final TextEditingController _controller = TextEditingController();

  @override
  Widget build(BuildContext context) {
    return Consumer<ChatbotProvider>(
      builder: (context, provider, child) {
        return Column(
          children: [
            if (provider.isLoading)
              CircularProgressIndicator(),

            if (provider.error != null)
              Text('에러: ${provider.error}', style: TextStyle(color: Colors.red)),

            if (provider.lastResponse != null)
              Text(provider.lastResponse!.answer ?? '이미지를 확인하세요'),

            TextField(
              controller: _controller,
              decoration: InputDecoration(hintText: '질문을 입력하세요'),
            ),

            ElevatedButton(
              onPressed: () {
                provider.askQuestion(_controller.text);
              },
              child: Text('질문하기'),
            ),
          ],
        );
      },
    );
  }
}
```

---

## 🌐 네트워크 설정

### Android

`android/app/src/main/AndroidManifest.xml`:

```xml
<manifest ...>
    <!-- 인터넷 권한 -->
    <uses-permission android:name="android.permission.INTERNET" />

    <application
        ...
        <!-- localhost 접근 허용 (디버그 빌드용) -->
        android:usesCleartextTraffic="true">
        ...
    </application>
</manifest>
```

**로컬 서버 접근 URL**:
- Android Emulator: `http://10.0.2.2:5000`
- 실제 디바이스 (같은 Wi-Fi): `http://[PC-IP]:5000` (예: `http://192.168.0.100:5000`)

### iOS

`ios/Runner/Info.plist`:

```xml
<dict>
    ...
    <!-- localhost HTTP 접근 허용 (디버그 빌드용) -->
    <key>NSAppTransportSecurity</key>
    <dict>
        <key>NSAllowsLocalNetworking</key>
        <true/>
        <key>NSAllowsArbitraryLoads</key>
        <true/>
    </dict>
</dict>
```

**로컬 서버 접근 URL**:
- iOS Simulator: `http://localhost:5000`
- 실제 디바이스 (같은 Wi-Fi): `http://[PC-IP]:5000`

---

## 📱 Flutter 완성 예제

```dart
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:io';

void main() {
  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'KNU 챗봇',
      home: ChatScreen(),
    );
  }
}

class ChatScreen extends StatefulWidget {
  @override
  _ChatScreenState createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final TextEditingController _controller = TextEditingController();
  final List<ChatMessage> _messages = [];
  bool _isLoading = false;

  // 플랫폼에 따라 base URL 설정
  String get baseUrl {
    if (Platform.isAndroid) {
      return 'http://10.0.2.2:5000'; // Android Emulator
    } else if (Platform.isIOS) {
      return 'http://localhost:5000'; // iOS Simulator
    } else {
      return 'http://localhost:5000'; // 기타
    }
  }

  Future<void> sendMessage(String question) async {
    if (question.trim().isEmpty) return;

    setState(() {
      _messages.add(ChatMessage(
        text: question,
        isUser: true,
      ));
      _isLoading = true;
    });

    _controller.clear();

    try {
      final response = await http.post(
        Uri.parse('$baseUrl/ai/ai-response'),
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
        },
        body: json.encode({'question': question}),
      );

      if (response.statusCode == 200) {
        final data = json.decode(utf8.decode(response.bodyBytes));

        setState(() {
          _messages.add(ChatMessage(
            text: data['answer'] ?? '이미지를 확인하세요',
            isUser: false,
            references: data['references'],
            images: List<String>.from(data['images']),
          ));
        });
      } else {
        final error = json.decode(response.body);
        throw Exception(error['error'] ?? 'Unknown error');
      }
    } catch (e) {
      setState(() {
        _messages.add(ChatMessage(
          text: '에러 발생: $e',
          isUser: false,
        ));
      });
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('KNU 컴퓨터학부 챗봇'),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final message = _messages[index];
                return ChatBubble(message: message);
              },
            ),
          ),
          if (_isLoading)
            Padding(
              padding: EdgeInsets.all(8.0),
              child: CircularProgressIndicator(),
            ),
          Padding(
            padding: EdgeInsets.all(8.0),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: InputDecoration(
                      hintText: '질문을 입력하세요',
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (text) => sendMessage(text),
                  ),
                ),
                SizedBox(width: 8),
                IconButton(
                  icon: Icon(Icons.send),
                  onPressed: () => sendMessage(_controller.text),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class ChatMessage {
  final String text;
  final bool isUser;
  final String? references;
  final List<String>? images;

  ChatMessage({
    required this.text,
    required this.isUser,
    this.references,
    this.images,
  });
}

class ChatBubble extends StatelessWidget {
  final ChatMessage message;

  const ChatBubble({required this.message});

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: message.isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: EdgeInsets.all(8),
        padding: EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: message.isUser ? Colors.blue[100] : Colors.grey[200],
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(message.text),
            if (message.references != null && !message.isUser)
              Padding(
                padding: EdgeInsets.only(top: 8),
                child: Text(
                  message.references!,
                  style: TextStyle(fontSize: 12, color: Colors.blue),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
```

---

## 🔒 보안 고려사항

### 프로덕션 배포 시

1. **HTTPS 사용**
   ```dart
   final baseUrl = 'https://your-domain.com';
   ```

2. **API 인증 추가 (선택사항)**
   ```dart
   headers: {
     'Content-Type': 'application/json',
     'Authorization': 'Bearer YOUR_API_KEY',
   }
   ```

3. **Cleartext Traffic 제거**
   - Android: `android:usesCleartextTraffic="false"`
   - iOS: `NSAllowsArbitraryLoads` 제거

---

## 📊 응답 시간

- **Health Check**: ~50ms
- **AI 응답**: 2-5초 (질문 복잡도에 따라 다름)
  - BM25 검색: ~1.5초
  - Pinecone 검색: ~0.6초
  - LLM 응답 생성: ~1-2초

### 타임아웃 설정 권장값

```dart
BaseOptions(
  connectTimeout: Duration(seconds: 10),
  receiveTimeout: Duration(seconds: 30), // AI 응답은 시간이 걸릴 수 있음
)
```

---

## 🧪 테스트

### cURL로 테스트

```bash
# Health Check
curl http://localhost:5000/health

# 챗봇 질문
curl -X POST http://localhost:5000/ai/ai-response \
  -H "Content-Type: application/json" \
  -d '{"question":"컴퓨터학부 졸업요건이 뭐야?"}'
```

### Flutter에서 실제 디바이스 테스트

1. PC와 모바일 기기를 **같은 Wi-Fi**에 연결
2. PC의 IP 주소 확인:
   - Windows: `ipconfig`
   - Mac/Linux: `ifconfig` 또는 `ip addr`
3. Flutter 앱에서 baseUrl 변경:
   ```dart
   final baseUrl = 'http://192.168.0.100:5000'; // PC IP로 변경
   ```

---

## 📝 추가 정보

- **API 버전**: 1.0.0
- **문자 인코딩**: UTF-8 (한글 지원)
- **최대 질문 길이**: 제한 없음 (권장: 500자 이내)
- **동시 요청**: 지원 (Flask 기본 동시성)

---

## 🐛 문제 해결

### "Failed host lookup" 에러

**원인**: 네트워크 연결 문제 또는 잘못된 URL

**해결**:
- Android Emulator: `10.0.2.2` 사용
- 실제 디바이스: PC IP 주소 확인

### "SocketException: OS Error: Connection refused"

**원인**: 서버가 실행되지 않음

**해결**:
```bash
docker-compose ps
# app 컨테이너가 실행 중인지 확인
```

### UTF-8 인코딩 문제

```dart
// ✅ 올바른 방법
final data = json.decode(utf8.decode(response.bodyBytes));

// ❌ 잘못된 방법 (한글 깨짐)
final data = json.decode(response.body);
```

---

## 📄 라이선스

이 API는 MIT 라이선스 하에 제공됩니다.
