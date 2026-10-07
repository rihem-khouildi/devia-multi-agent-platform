"""
JavaTemplateEngine
==================
Génère tous les fichiers boilerplate Spring Boot en Python pur,
à partir de l'AnalysisResult produit par l'Advisor.

═══════════════════════════════════════════════════════════
PRINCIPE FONDAMENTAL: SÉPARATION STRICTE
═══════════════════════════════════════════════════════════
Ce moteur génère le code boilerplate en Python pur (SANS LLM).
Ce code est TOUJOURS CORRECT par construction et ne doit JAMAIS
être modifié par un LLM ou un sanitizer.

FICHIERS GÉNÉRÉS (Python pur - toujours corrects):
═══════════════════════════════════════════════════════════
✓ Application.java               - Point d'entrée Spring Boot
✓ OpenApiConfig.java             - Configuration Swagger/OpenAPI
✓ controller/HealthCheckController.java - Endpoint "Hello World" de test
✓ exception/ResourceNotFoundException.java
✓ exception/BusinessException.java
✓ exception/ErrorResponse.java
✓ exception/GlobalExceptionHandler.java
✓ application.properties          - Configuration Spring
✓ pom.xml                        - Dépendances Maven

FICHIERS NON GÉNÉRÉS (délégués au DeveloperAgent/LLM):
═══════════════════════════════════════════════════════════
✗ Entity.java                    - Logique métier spécifique
✗ Repository.java                - Queries custom
✗ Service.java / ServiceImpl.java - Logique métier
✗ Controller.java                - Endpoints spécifiques
✗ RequestDTO.java / ResponseDTO.java - Champs spécifiques

RÈGLE ABSOLUE:
═══════════════════════════════════════════════════════════
Le Developer LLM ne génère QUE la logique métier.
Si une erreur est détectée dans un fichier boilerplate, c'est
un bug dans ce moteur Python (pas dans le LLM).
→ Le LLM ne corrige JAMAIS les fichiers de ce moteur.
"""

from typing import Dict
from core.models import AnalysisResult


class JavaTemplateEngine:
    """Génère les fichiers boilerplate Spring Boot sans LLM."""

    def __init__(self, analysis: AnalysisResult):
        self.analysis = analysis
        self.pkg = analysis.package_base
        self.base = f"src/main/java/{self.pkg.replace('.', '/')}"
        self.group_id = self.pkg.rsplit(".", 1)[0] if "." in self.pkg else self.pkg
        self.artifact_id = f"{analysis.service_name.lower()}-service"
        self.has_jpa = any(
            "jpa" in d.lower() or "data" in d.lower()
            for d in analysis.dependencies
        ) or len(analysis.entities) > 0

    def generate_all(self) -> Dict[str, str]:
        """Retourne tous les fichiers boilerplate prêts à l'emploi."""
        files = {}
        files[f"{self.base}/Application.java"] = self._application()
        files[f"{self.base}/OpenApiConfig.java"] = self._openapi_config()
        files[f"{self.base}/controller/HealthCheckController.java"] = self._health_check_controller()
        files[f"{self.base}/exception/ResourceNotFoundException.java"] = self._resource_not_found()
        files[f"{self.base}/exception/BusinessException.java"] = self._business_exception()
        files[f"{self.base}/exception/ErrorResponse.java"] = self._error_response()
        files[f"{self.base}/exception/GlobalExceptionHandler.java"] = self._global_exception_handler()
        files["src/main/resources/application.properties"] = self._application_properties()
        return files

    def generate_pom(self) -> str:
        """Retourne le pom.xml complet."""
        extra_deps = ""
        if self.has_jpa:
            extra_deps = """
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>"""

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
        <relativePath/>
    </parent>

    <groupId>{self.group_id}</groupId>
    <artifactId>{self.artifact_id}</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>
    <name>{self.artifact_id}</name>

    <properties>
        <java.version>21</java.version>
        <lombok.version>1.18.32</lombok.version>
        <mapstruct.version>1.5.5.Final</mapstruct.version>
        <springdoc.version>2.3.0</springdoc.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>{extra_deps}
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <version>${{lombok.version}}</version>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.mapstruct</groupId>
            <artifactId>mapstruct</artifactId>
            <version>${{mapstruct.version}}</version>
        </dependency>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>${{springdoc.version}}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
                <configuration>
                    <excludes>
                        <exclude>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                        </exclude>
                    </excludes>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.projectlombok</groupId>
                            <artifactId>lombok</artifactId>
                            <version>${{lombok.version}}</version>
                        </path>
                        <path>
                            <groupId>org.mapstruct</groupId>
                            <artifactId>mapstruct-processor</artifactId>
                            <version>${{mapstruct.version}}</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.11</version>
                <configuration>
                    <excludes>
                        <exclude>{self.pkg.replace('.', '/')}/Application*</exclude>
                        <exclude>{self.pkg.replace('.', '/')}/OpenApiConfig*</exclude>
                        <exclude>{self.pkg.replace('.', '/')}/controller/HealthCheckController*</exclude>
                        <exclude>{self.pkg.replace('.', '/')}/dto/*</exclude>
                        <exclude>{self.pkg.replace('.', '/')}/entity/*</exclude>
                        <exclude>{self.pkg.replace('.', '/')}/repository/*</exclude>
                        <exclude>{self.pkg.replace('.', '/')}/exception/*</exclude>
                    </excludes>
                </configuration>
                <executions>
                    <execution>
                        <goals><goal>prepare-agent</goal></goals>
                    </execution>
                    <execution>
                        <id>report</id>
                        <phase>test</phase>
                        <goals><goal>report</goal></goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>"""

    # ──────────────────────────────────────────────────────────────
    #  Templates des fichiers boilerplate
    # ──────────────────────────────────────────────────────────────

    def _application(self) -> str:
        return f"""package {self.pkg};

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {{

    public static void main(String[] args) {{
        SpringApplication.run(Application.class, args);
    }}
}}
"""

    def _openapi_config(self) -> str:
        return f"""package {self.pkg};

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {{

    @Bean
    public OpenAPI customOpenAPI() {{
        return new OpenAPI()
                .info(new Info()
                        .title("{self.analysis.service_name} API")
                        .version("1.0.0")
                        .description("API générée par AI-SDLC Pipeline")
                        .contact(new Contact()
                                .name("AI-SDLC")
                                .email("ai-sdlc@example.com")));
    }}
}}
"""

    def _health_check_controller(self) -> str:
        """Génère un controller de test pour valider que l'application fonctionne."""
        return f"""package {self.pkg}.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;

import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.Map;

/**
 * Controller de santé pour vérifier que l'application fonctionne.
 * Ce controller est généré automatiquement par le JavaTemplateEngine.
 */
@RestController
@RequestMapping("/")
@Tag(name = "Health Check", description = "Endpoints de vérification de l'application")
public class HealthCheckController {{

    @GetMapping
    @Operation(
        summary = "Hello World - Endpoint racine",
        description = "Retourne un message de bienvenue pour confirmer que l'application fonctionne"
    )
    public ResponseEntity<Map<String, Object>> helloWorld() {{
        Map<String, Object> response = new HashMap<>();
        response.put("message", "Hello World! 🚀");
        response.put("service", "{self.analysis.service_name}");
        response.put("status", "✅ Application is running");
        response.put("timestamp", LocalDateTime.now().toString());
        response.put("documentation", "http://localhost:8080/swagger-ui.html");

        return ResponseEntity.ok(response);
    }}

    @GetMapping("/health")
    @Operation(
        summary = "Health check",
        description = "Vérifie l'état de santé de l'application"
    )
    public ResponseEntity<Map<String, String>> health() {{
        Map<String, String> response = new HashMap<>();
        response.put("status", "UP");
        response.put("service", "{self.analysis.service_name}");
        response.put("timestamp", LocalDateTime.now().toString());

        return ResponseEntity.ok(response);
    }}
}}
"""

    def _resource_not_found(self) -> str:
        return f"""package {self.pkg}.exception;

public class ResourceNotFoundException extends RuntimeException {{

    public ResourceNotFoundException(String message) {{
        super(message);
    }}

    public ResourceNotFoundException(String resourceName, String fieldName, Object fieldValue) {{
        super(String.format("%s not found with %s : '%s'", resourceName, fieldName, fieldValue));
    }}
}}
"""

    def _business_exception(self) -> str:
        return f"""package {self.pkg}.exception;

public class BusinessException extends RuntimeException {{

    private final int statusCode;

    public BusinessException(String message) {{
        super(message);
        this.statusCode = 400;
    }}

    public BusinessException(String message, int statusCode) {{
        super(message);
        this.statusCode = statusCode;
    }}

    public int getStatusCode() {{
        return statusCode;
    }}
}}
"""

    def _error_response(self) -> str:
        return f"""package {self.pkg}.exception;

public class ErrorResponse {{
    private int status;
    private String message;
    private String timestamp;

    public ErrorResponse() {{}}

    public ErrorResponse(int status, String message, String timestamp) {{
        this.status = status;
        this.message = message;
        this.timestamp = timestamp;
    }}

    public int getStatus() {{
        return status;
    }}

    public void setStatus(int status) {{
        this.status = status;
    }}

    public String getMessage() {{
        return message;
    }}

    public void setMessage(String message) {{
        this.message = message;
    }}

    public String getTimestamp() {{
        return timestamp;
    }}

    public void setTimestamp(String timestamp) {{
        this.timestamp = timestamp;
    }}
}}
"""

    def _global_exception_handler(self) -> str:
        return f"""package {self.pkg}.exception;

import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.bind.annotation.ExceptionHandler;

import java.time.LocalDateTime;
import java.util.stream.Collectors;

@Slf4j
@ControllerAdvice
public class GlobalExceptionHandler {{

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleResourceNotFound(ResourceNotFoundException ex) {{
        log.error("Resource not found: {{}}", ex.getMessage());
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(buildError(HttpStatus.NOT_FOUND.value(), ex.getMessage()));
    }}

    @ExceptionHandler(BusinessException.class)
    public ResponseEntity<ErrorResponse> handleBusinessException(BusinessException ex) {{
        log.error("Business error: {{}}", ex.getMessage());
        return ResponseEntity.status(ex.getStatusCode())
                .body(buildError(ex.getStatusCode(), ex.getMessage()));
    }}

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidation(MethodArgumentNotValidException ex) {{
        String message = ex.getBindingResult().getFieldErrors().stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .collect(Collectors.joining(", "));
        log.error("Validation error: {{}}", message);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                .body(buildError(HttpStatus.BAD_REQUEST.value(), message));
    }}

    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneric(Exception ex) {{
        log.error("Unexpected error: {{}}", ex.getMessage(), ex);
        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(buildError(HttpStatus.INTERNAL_SERVER_ERROR.value(), "An unexpected error occurred"));
    }}

    private ErrorResponse buildError(int status, String message) {{
        return new ErrorResponse(status, message, LocalDateTime.now().toString());
    }}
}}
"""

    def _application_properties(self) -> str:
        jpa_config = ""
        if self.has_jpa:
            jpa_config = """
# H2 in-memory database (dev)
spring.datasource.url=jdbc:h2:mem:testdb
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.database-platform=org.hibernate.dialect.H2Dialect
spring.h2.console.enabled=true
spring.h2.console.path=/h2-console

# JPA
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true"""

        return f"""spring.application.name={self.analysis.service_name.lower()}
server.port=8080
{jpa_config}
# Swagger UI
springdoc.api-docs.path=/api-docs
springdoc.swagger-ui.path=/swagger-ui.html
springdoc.swagger-ui.enabled=true
"""
