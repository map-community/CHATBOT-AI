# KNU 챗봇 AI 서버 API 명세서

경북대학교 컴퓨터학부 챗봇 AI 서버와 통신하기 위한 REST API 명세서입니다.

## 📌 기본 정보

| 항목 | 값 |
|------|-----|
| **Base URL** | `http://172.31.37.76:5000` (Private IP) |
| **프로토콜** | HTTP |
| **인증** | 없음 (AWS 보안 그룹으로 제어) |
| **데이터 형식** | JSON |
| **문자 인코딩** | UTF-8 |
| **타임아웃** | 30초 권장 |

> ⚠️ **주의**: 반드시 **Private IP**를 사용하세요. Public IP 사용 시 보안 그룹 차단됩니다.

---

## 🔌 엔드포인트 목록

| 메서드 | 경로 | 설명 | 응답 시간 |
|--------|------|------|----------|
| GET | `/health` | 서버 상태 확인 | < 100ms |
| POST | `/ai/ai-response` | AI 챗봇 응답 생성 | 3-10초 |

---

## 1️⃣ Health Check

서버가 정상 작동 중인지 확인합니다.

### Request

```http
GET /health HTTP/1.1
Host: 172.31.37.76:5000
```

### Response

**200 OK**

```json
{
  "status": "healthy",
  "message": "KNU Chatbot Server is running",
  "version": "1.0.0"
}
```

### Spring Boot 예제

```java
@Service
public class AiChatbotHealthService {

    @Value("${ai.chatbot.base-url}")
    private String aiBaseUrl;

    private final RestTemplate restTemplate;

    public boolean isHealthy() {
        try {
            ResponseEntity<HealthResponse> response = restTemplate.getForEntity(
                aiBaseUrl + "/health",
                HealthResponse.class
            );

            return response.getStatusCode() == HttpStatus.OK
                && "healthy".equals(response.getBody().getStatus());
        } catch (Exception e) {
            log.error("AI 서버 Health Check 실패", e);
            return false;
        }
    }

    @Data
    static class HealthResponse {
        private String status;
        private String message;
        private String version;
    }
}
```

---

## 2️⃣ AI 챗봇 응답 생성

사용자 질문에 대한 AI 답변을 생성합니다.

### Request

```http
POST /ai/ai-response HTTP/1.1
Host: 172.31.37.76:5000
Content-Type: application/json

{
  "question": "컴퓨터학부 사무실 어디야?"
}
```

#### Request Body

| 필드 | 타입 | 필수 | 설명 | 제약사항 |
|------|------|------|------|----------|
| `question` | string | ✅ | 사용자의 질문 | 1자 이상, 공백 제거 후 빈 문자열 불가 |

#### 유효한 요청 예시

```json
{
  "question": "소프트웨어학과 교수님 명단 알려줘"
}
```

```json
{
  "question": "2024년 1학기 학사일정"
}
```

```json
{
  "question": "AI/빅데이터 전공 커리큘럼"
}
```

---

### Response

#### 성공 응답

**200 OK**

```json
{
  "answer": "컴퓨터학부 사무실은 IT대학 1호관 302호에 위치해 있습니다.\n\n운영 시간:\n- 평일: 09:00 ~ 18:00\n- 점심시간: 12:00 ~ 13:00\n\n연락처: 053-950-5550",
  "references": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=29832",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": [
    "https://cse.knu.ac.kr/image/office_map.png",
    "https://cse.knu.ac.kr/image/office_hours.jpg"
  ]
}
```

#### Response Body

| 필드 | 타입 | 설명 | 가능한 값 |
|------|------|------|----------|
| `answer` | string \| null | AI가 생성한 답변 텍스트 | - 일반 답변 텍스트<br>- `null` (이미지만 있는 경우) |
| `references` | string | 참고 URL | - 단일 URL<br>- 게시판 Base URL |
| `disclaimer` | string | 면책 조항 | 고정 문구 |
| `images` | array[string] | 관련 이미지 URL 목록 | - 이미지 URL 배열<br>- `["No content"]` (없는 경우) |

---

### 응답 패턴 (시나리오별)

#### 1️⃣ 일반 답변 (텍스트 + 이미지)

```json
{
  "answer": "2024학년도 1학기 기말고사 일정은 6월 17일(월)부터 6월 21일(금)까지입니다.",
  "references": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=29845",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": ["https://cse.knu.ac.kr/data/file/sub5_1/schedule_2024.png"]
}
```

#### 2️⃣ 이미지만 있는 경우

```json
{
  "answer": null,
  "references": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=28965",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": [
    "https://cse.knu.ac.kr/data/file/sub5_1/poster1.jpg",
    "https://cse.knu.ac.kr/data/file/sub5_1/poster2.jpg"
  ]
}
```

> 💡 **UI 처리**: `answer`가 `null`이면 이미지만 표시하고, 텍스트는 "자세한 내용은 이미지를 참고하세요" 등으로 대체

#### 3️⃣ 목록형 답변 (공지사항/채용 등)

```json
{
  "answer": "'공지사항'에 대한 정보 목록입니다:\n\n제목: [필독] 2024-1학기 수강신청 안내, 날짜: 2024-01-15 \n----------------------------------------------------\n제목: 학부생 연구참여 프로그램 모집, 날짜: 2024-01-20 \n----------------------------------------------------\n제목: 컴퓨터학부 MT 안내, 날짜: 2024-03-02 \n----------------------------------------------------\n",
  "references": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1&wr_id=",
  "disclaimer": "\n\n항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": ["No content"]
}
```

#### 4️⃣ 결과 없음 (공지사항에 없는 내용)

```json
{
  "answer": "해당 질문은 공지사항에 없는 내용입니다.\n 자세한 사항은 공지사항을 살펴봐주세요.",
  "references": "https://cse.knu.ac.kr/bbs/board.php?bo_table=sub5_1",
  "disclaimer": "항상 정확한 답변을 제공하지 못할 수 있습니다. 아래의 URL들을 참고하여 정확하고 자세한 정보를 확인하세요.",
  "images": ["No content"]
}
```

---

### 에러 응답

#### 400 Bad Request (잘못된 요청)

```json
{
  "error": "Invalid or missing question"
}
```

**발생 조건:**
- `question` 필드가 없음
- `question`이 빈 문자열 또는 공백만 있음
- `question`이 문자열 타입이 아님
- JSON 형식이 잘못됨

#### 500 Internal Server Error (서버 오류)

```json
{
  "error": "Unexpected error occurred during AI processing"
}
```

**발생 조건:**
- AI 모델 처리 중 예외 발생
- DB 연결 실패
- Pinecone/Upstage API 오류

---

## 🔧 Spring Boot 통합 가이드

### 1. 의존성 추가

```gradle
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Optional: WebClient 사용 시 (비동기)
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

### 2. Configuration

```java
@Configuration
public class AiChatbotConfig {

    @Value("${ai.chatbot.base-url}")
    private String baseUrl;

    @Value("${ai.chatbot.timeout}")
    private int timeout;

    @Bean
    public RestTemplate aiRestTemplate() {
        HttpComponentsClientHttpRequestFactory factory =
            new HttpComponentsClientHttpRequestFactory();
        factory.setConnectTimeout(5000);  // 5초
        factory.setReadTimeout(timeout);   // 30초

        return new RestTemplate(factory);
    }

    // 또는 WebClient (비동기)
    @Bean
    public WebClient aiWebClient() {
        return WebClient.builder()
            .baseUrl(baseUrl)
            .defaultHeader(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE)
            .build();
    }
}
```

### 3. DTO 정의

```java
// Request DTO
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AiQuestionRequest {
    @NotBlank(message = "질문은 필수입니다")
    private String question;
}

// Response DTO
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AiAnswerResponse {
    private String answer;          // null 가능
    private String references;
    private String disclaimer;
    private List<String> images;

    public boolean hasAnswer() {
        return answer != null && !answer.trim().isEmpty();
    }

    public boolean hasImages() {
        return images != null
            && !images.isEmpty()
            && !images.get(0).equals("No content");
    }
}

// Error Response DTO
@Data
@NoArgsConstructor
@AllArgsConstructor
public class AiErrorResponse {
    private String error;
}
```

### 4. Service 구현 (RestTemplate)

```java
@Service
@Slf4j
public class AiChatbotService {

    @Value("${ai.chatbot.base-url}")
    private String aiBaseUrl;

    private final RestTemplate aiRestTemplate;

    public AiChatbotService(RestTemplate aiRestTemplate) {
        this.aiRestTemplate = aiRestTemplate;
    }

    public AiAnswerResponse getAnswer(String question) {
        String url = aiBaseUrl + "/ai/ai-response";

        AiQuestionRequest request = new AiQuestionRequest(question);

        try {
            log.info("AI 서버 요청 시작: question={}", question);
            long startTime = System.currentTimeMillis();

            ResponseEntity<AiAnswerResponse> response = aiRestTemplate.postForEntity(
                url,
                request,
                AiAnswerResponse.class
            );

            long elapsed = System.currentTimeMillis() - startTime;
            log.info("AI 서버 응답 완료: {}ms", elapsed);

            if (response.getStatusCode() == HttpStatus.OK) {
                return response.getBody();
            } else {
                throw new AiServerException("AI 서버 응답 실패: " + response.getStatusCode());
            }

        } catch (HttpClientErrorException e) {
            log.error("AI 서버 요청 오류 (400): {}", e.getResponseBodyAsString());
            throw new IllegalArgumentException("잘못된 질문 형식입니다");

        } catch (HttpServerErrorException e) {
            log.error("AI 서버 내부 오류 (500): {}", e.getResponseBodyAsString());
            throw new AiServerException("AI 서버 처리 중 오류가 발생했습니다");

        } catch (ResourceAccessException e) {
            log.error("AI 서버 연결 실패: {}", e.getMessage());
            throw new AiServerException("AI 서버에 연결할 수 없습니다");
        }
    }
}

@ResponseStatus(HttpStatus.SERVICE_UNAVAILABLE)
class AiServerException extends RuntimeException {
    public AiServerException(String message) {
        super(message);
    }
}
```

### 5. Service 구현 (WebClient - 비동기)

```java
@Service
@Slf4j
public class AiChatbotWebClientService {

    private final WebClient aiWebClient;

    public AiChatbotWebClientService(WebClient aiWebClient) {
        this.aiWebClient = aiWebClient;
    }

    public Mono<AiAnswerResponse> getAnswerAsync(String question) {
        AiQuestionRequest request = new AiQuestionRequest(question);

        return aiWebClient.post()
            .uri("/ai/ai-response")
            .bodyValue(request)
            .retrieve()
            .onStatus(
                HttpStatus::is4xxClientError,
                response -> response.bodyToMono(AiErrorResponse.class)
                    .flatMap(error -> Mono.error(
                        new IllegalArgumentException("잘못된 요청: " + error.getError())
                    ))
            )
            .onStatus(
                HttpStatus::is5xxServerError,
                response -> Mono.error(
                    new AiServerException("AI 서버 오류")
                )
            )
            .bodyToMono(AiAnswerResponse.class)
            .doOnSuccess(response -> log.info("AI 응답 성공"))
            .doOnError(error -> log.error("AI 요청 실패", error));
    }
}
```

### 6. Controller 예제

```java
@RestController
@RequestMapping("/api/chatbot")
@Slf4j
public class ChatbotController {

    private final AiChatbotService aiChatbotService;

    public ChatbotController(AiChatbotService aiChatbotService) {
        this.aiChatbotService = aiChatbotService;
    }

    @PostMapping("/ask")
    public ResponseEntity<AiAnswerResponse> askQuestion(
        @RequestBody @Valid AiQuestionRequest request
    ) {
        try {
            AiAnswerResponse answer = aiChatbotService.getAnswer(request.getQuestion());
            return ResponseEntity.ok(answer);

        } catch (IllegalArgumentException e) {
            log.warn("잘못된 요청: {}", e.getMessage());
            return ResponseEntity.badRequest().build();

        } catch (AiServerException e) {
            log.error("AI 서버 오류: {}", e.getMessage());
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
        }
    }

    // Health check 전달
    @GetMapping("/health")
    public ResponseEntity<String> healthCheck() {
        try {
            ResponseEntity<String> response = aiRestTemplate.getForEntity(
                aiBaseUrl + "/health",
                String.class
            );
            return ResponseEntity.ok(response.getBody());
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body("{\"status\":\"unhealthy\"}");
        }
    }
}
```

---

## 🎨 프론트엔드 연동 (Thymeleaf SSR 예제)

### Controller (SSR)

```java
@Controller
@RequestMapping("/chatbot")
public class ChatbotViewController {

    private final AiChatbotService aiChatbotService;

    @GetMapping
    public String chatbotPage(Model model) {
        return "chatbot/index";  // templates/chatbot/index.html
    }

    @PostMapping("/ask")
    @ResponseBody
    public AiAnswerResponse askQuestion(@RequestParam String question) {
        return aiChatbotService.getAnswer(question);
    }
}
```

### Thymeleaf Template

```html
<!DOCTYPE html>
<html xmlns:th="http://www.thymeleaf.org">
<head>
    <title>KNU 챗봇</title>
    <style>
        .chat-container { max-width: 800px; margin: 0 auto; }
        .message { padding: 10px; margin: 10px 0; border-radius: 5px; }
        .user { background: #e3f2fd; text-align: right; }
        .ai { background: #f5f5f5; }
        .images img { max-width: 300px; margin: 5px; }
    </style>
</head>
<body>
    <div class="chat-container">
        <h1>경북대 컴퓨터학부 챗봇</h1>

        <div id="chat-messages"></div>

        <form id="chat-form">
            <input type="text" id="question" placeholder="질문을 입력하세요" required>
            <button type="submit">전송</button>
        </form>
    </div>

    <script>
        document.getElementById('chat-form').addEventListener('submit', async (e) => {
            e.preventDefault();

            const question = document.getElementById('question').value;
            const messagesDiv = document.getElementById('chat-messages');

            // 사용자 메시지 표시
            messagesDiv.innerHTML += `
                <div class="message user">
                    <strong>나:</strong> ${question}
                </div>
            `;

            // AI 서버 호출
            try {
                const response = await fetch('/chatbot/ask', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                    body: `question=${encodeURIComponent(question)}`
                });

                const data = await response.json();

                // AI 응답 표시
                let aiHtml = '<div class="message ai"><strong>챗봇:</strong><br>';

                if (data.answer) {
                    aiHtml += `<p>${data.answer.replace(/\n/g, '<br>')}</p>`;
                }

                if (data.images && data.images[0] !== 'No content') {
                    aiHtml += '<div class="images">';
                    data.images.forEach(img => {
                        aiHtml += `<img src="${img}" alt="참고 이미지">`;
                    });
                    aiHtml += '</div>';
                }

                aiHtml += `<p><small><a href="${data.references}" target="_blank">📎 원문 보기</a></small></p>`;
                aiHtml += '</div>';

                messagesDiv.innerHTML += aiHtml;

            } catch (error) {
                messagesDiv.innerHTML += `
                    <div class="message ai" style="background:#ffebee">
                        <strong>오류:</strong> AI 서버 연결 실패
                    </div>
                `;
            }

            // 입력창 초기화
            document.getElementById('question').value = '';
        });
    </script>
</body>
</html>
```

---

## ⏱️ 성능 특성

| 작업 | 평균 응답 시간 | 최대 응답 시간 |
|------|---------------|---------------|
| Health Check | 50-100ms | 500ms |
| 일반 질문 | 3-5초 | 10초 |
| 복잡한 질문 (이미지 많음) | 5-8초 | 15초 |
| 최초 요청 (캐시 없음) | 5-10초 | 20초 |

**권장 타임아웃**: 30초

---

## 🚨 에러 처리 가이드

### 1. 타임아웃 처리

```java
try {
    return aiChatbotService.getAnswer(question);
} catch (ResourceAccessException e) {
    // 타임아웃 또는 연결 실패
    return AiAnswerResponse.builder()
        .answer("죄송합니다. 현재 AI 서버가 응답하지 않습니다. 잠시 후 다시 시도해주세요.")
        .references("https://cse.knu.ac.kr")
        .disclaimer("서비스 일시 중단")
        .images(List.of("No content"))
        .build();
}
```

### 2. 재시도 로직

```java
@Service
public class ResilientAiChatbotService {

    private final AiChatbotService aiChatbotService;

    @Retryable(
        value = {ResourceAccessException.class},
        maxAttempts = 3,
        backoff = @Backoff(delay = 2000)  // 2초 간격
    )
    public AiAnswerResponse getAnswerWithRetry(String question) {
        return aiChatbotService.getAnswer(question);
    }

    @Recover
    public AiAnswerResponse recover(ResourceAccessException e, String question) {
        log.error("3회 재시도 후 실패: {}", e.getMessage());
        return createFallbackResponse();
    }
}
```

---

## 📊 모니터링

### 로그 예시

```log
2024-11-20 10:15:23 INFO  AiChatbotService - AI 서버 요청 시작: question=컴퓨터학부 사무실 어디야?
2024-11-20 10:15:27 INFO  AiChatbotService - AI 서버 응답 완료: 4235ms
```

### 메트릭 수집 (Actuator)

```java
@Component
public class AiChatbotMetrics {

    private final MeterRegistry meterRegistry;
    private final Counter requestCounter;
    private final Timer responseTimer;

    public AiChatbotMetrics(MeterRegistry meterRegistry) {
        this.meterRegistry = meterRegistry;
        this.requestCounter = Counter.builder("ai.chatbot.requests")
            .description("AI 챗봇 요청 횟수")
            .register(meterRegistry);
        this.responseTimer = Timer.builder("ai.chatbot.response.time")
            .description("AI 챗봇 응답 시간")
            .register(meterRegistry);
    }
}
```

---

## 🔗 참고 자료

- [AWS 보안 그룹 설정 가이드](./AWS_SECURITY_SETUP.md)
- [AI 서버 배포 가이드](./EC2_DEPLOYMENT_GUIDE.md)
- Spring RestTemplate 공식 문서
- Spring WebClient 공식 문서

---

## 📞 지원

문의사항이 있으시면 AI 서버 관리자에게 연락하세요.

**최종 수정일**: 2024-11-20
