# Base Spring Project

Clean Spring Boot base project for the AI-SDLC pipeline.

This project is intentionally minimal. It does not contain generated user-story features such as User, Authentication, or HelloWorld.

## Run locally

```powershell
mvn clean compile
mvn test
mvn spring-boot:run
```

Health endpoint:

```text
GET http://localhost:8080/api/health
```
